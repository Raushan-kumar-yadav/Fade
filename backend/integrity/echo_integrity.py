 
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sqlite3
import sys
import time
import uuid
from pathlib import Path

 
_LEAF, _NODE = b"\x00", b"\x01"


def sha256_file(path: str | os.PathLike, chunk_size: int = 1 << 20) -> str:
    """Stream the file in 1 MB chunks so big videos don't need to fit in RAM."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(chunk_size), b""):
            h.update(block)
    return h.hexdigest()


def leaf_hash(file_sha256: str) -> str:
    return hashlib.sha256(_LEAF + bytes.fromhex(file_sha256)).hexdigest()


def node_hash(left: str, right: str) -> str:
    return hashlib.sha256(_NODE + bytes.fromhex(left) + bytes.fromhex(right)).hexdigest()


def build_tree(leaves: list[str]) -> list[list[str]]:
    """Return every level of the tree, leaves first, root level last.
    An odd node is promoted unchanged (never duplicated)."""
    if not leaves:
        raise ValueError("cannot build a Merkle tree with no leaves")
    levels = [list(leaves)]
    while len(levels[-1]) > 1:
        cur, nxt = levels[-1], []
        for i in range(0, len(cur), 2):
            nxt.append(node_hash(cur[i], cur[i + 1]) if i + 1 < len(cur) else cur[i])
        levels.append(nxt)
    return levels


def get_proof(levels: list[list[str]], index: int) -> list[dict]:
    """Sibling hashes from leaf to root. 'side' = where the sibling sits."""
    proof = []
    for level in levels[:-1]:
        sib = index ^ 1
        if sib < len(level):
            proof.append({"hash": level[sib], "side": "left" if sib < index else "right"})
        index //= 2
    return proof


def fold_proof(leaf: str, proof: list[dict]) -> str:
    """Recompute the root from a leaf and its proof."""
    cur = leaf
    for step in proof:
        cur = node_hash(step["hash"], cur) if step["side"] == "left" else node_hash(cur, step["hash"])
    return cur


 
class LocalLedger:
    """File-backed, hash-chained ledger. A stand-in so you can develop and test with
    no wallet, gas or network. It is tamper-EVIDENT for casual edits but NOT a real
    blockchain - whoever owns the machine could rewrite the whole file. Use EVMLedger
    for the real anchoring."""

    GENESIS = "0" * 64

    def __init__(self, path: str | os.PathLike):
        self.path = Path(path)

    def _blocks(self) -> list[dict]:
        if not self.path.exists():
            return []
        return [json.loads(line) for line in self.path.read_text().splitlines() if line.strip()]

    @staticmethod
    def _block_hash(b: dict) -> str:
        body = {k: b[k] for k in ("height", "prev_hash", "root", "timestamp")}
        return hashlib.sha256(json.dumps(body, sort_keys=True, separators=(",", ":")).encode()).hexdigest()

    def anchor(self, root: str) -> dict:
        blocks = self._blocks()
        b = {
            "height": len(blocks) + 1,
            "prev_hash": blocks[-1]["hash"] if blocks else self.GENESIS,
            "root": root,
            "timestamp": int(time.time()),
        }
        b["hash"] = self._block_hash(b)
        with open(self.path, "a") as f:
            f.write(json.dumps(b) + "\n")
        return {"tx": b["hash"], "height": b["height"]}

    def validate(self) -> tuple[bool, str]:
        prev = self.GENESIS
        for b in self._blocks():
            if b["prev_hash"] != prev or b["hash"] != self._block_hash(b):
                return False, f"ledger broken at block {b['height']}"
            prev = b["hash"]
        return True, "ledger intact"

    def lookup(self, root: str) -> dict:
        ok, msg = self.validate()
        if not ok:
            return {"anchored": False, "error": msg}
        for b in self._blocks():
            if b["root"] == root:
                return {"anchored": True, "timestamp": b["timestamp"], "height": b["height"], "tx": b["hash"]}
        return {"anchored": False}


class EVMLedger:
    """Anchors roots in the ArtifactRegistry.sol contract via web3.py.
    pip install web3   |   NOTE: not exercised by the bundled tests (needs a live RPC)."""

    def __init__(self, rpc_url: str, contract_address: str, private_key: str,
                 abi_path: str = "ArtifactRegistry.abi.json"):
        from web3 import Web3  # imported lazily so the rest works without web3 installed

        self.w3 = Web3(Web3.HTTPProvider(rpc_url))
        self.acct = self.w3.eth.account.from_key(private_key)
        with open(abi_path) as f:
            abi = json.load(f)
        self.contract = self.w3.eth.contract(address=Web3.to_checksum_address(contract_address), abi=abi)

    def anchor(self, root: str) -> dict:
        tx = self.contract.functions.anchorRoot(bytes.fromhex(root)).build_transaction(
            {"from": self.acct.address, "nonce": self.w3.eth.get_transaction_count(self.acct.address)}
        )
        signed = self.acct.sign_transaction(tx)
        raw = getattr(signed, "raw_transaction", None) or signed.rawTransaction
        receipt = self.w3.eth.wait_for_transaction_receipt(self.w3.eth.send_raw_transaction(raw))
        return {"tx": receipt.transactionHash.hex(), "height": receipt.blockNumber}

    def lookup(self, root: str) -> dict:
        anchored, ts = self.contract.functions.isAnchored(bytes.fromhex(root)).call()
        return {"anchored": bool(anchored), "timestamp": ts}



# Verification (needs only: the file, a proof bundle, and the ledger)

def verify_bundle(path: str, bundle: dict, ledger) -> dict:
    """The ledger is the only thing trusted. The local DB is NOT: a forged proof can't
    produce a root that is actually anchored."""
    now = sha256_file(path)
    hash_ok = now == bundle["sha256"]
    proof_ok = fold_proof(leaf_hash(now), bundle["proof"]) == bundle["root"]
    chain = ledger.lookup(bundle["root"])
    anchored = bool(chain.get("anchored"))

    checks = [
        ("file hash equals the registered hash", hash_ok),
        ("Merkle proof leads to the recorded root", proof_ok),
        ("root is anchored on the ledger", anchored),
    ]
    if hash_ok and proof_ok and anchored:
        verdict = "AUTHENTIC"
    elif not (hash_ok and proof_ok):
        verdict = "TAMPERED"
    else:
        verdict = "ROOT_NOT_ON_LEDGER"
    return {"verdict": verdict, "checks": checks, "current_sha256": now,
            "anchor": chain, "artifact_id": bundle.get("artifact_id")}



# 4. Service: register -> seal -> verify / export
class Integrity:
    def __init__(self, db_path: str | os.PathLike, ledger):
        self.ledger = ledger
        self.db = sqlite3.connect(str(db_path))
        self.db.row_factory = sqlite3.Row
        self.db.executescript(
            """
            CREATE TABLE IF NOT EXISTS artifacts(
                id TEXT PRIMARY KEY, filename TEXT, sha256 TEXT, size INTEGER,
                registered_at INTEGER, batch_id INTEGER, leaf_index INTEGER, proof TEXT);
            CREATE TABLE IF NOT EXISTS batches(
                id INTEGER PRIMARY KEY AUTOINCREMENT, root TEXT, leaf_count INTEGER,
                sealed_at INTEGER, tx TEXT, height INTEGER);
            """
        )

    def register(self, path: str) -> dict:
        """Hash a file and queue it for the next batch. Nothing is stored but the hash + name."""
        rec = {
            "id": uuid.uuid4().hex[:12],
            "filename": os.path.basename(path),
            "sha256": sha256_file(path),
            "size": os.path.getsize(path),
            "registered_at": int(time.time()),
        }
        self.db.execute(
            "INSERT INTO artifacts(id, filename, sha256, size, registered_at) VALUES(:id,:filename,:sha256,:size,:registered_at)",
            rec,
        )
        self.db.commit()
        return rec

    def seal(self) -> dict | None:
        """Build one Merkle tree over every pending artifact and anchor its root."""
        rows = self.db.execute("SELECT * FROM artifacts WHERE batch_id IS NULL ORDER BY rowid").fetchall()
        if not rows:
            return None
        levels = build_tree([leaf_hash(r["sha256"]) for r in rows])
        root = levels[-1][0]
        # Idempotent: if we crashed after anchoring last time, reuse the existing anchor.
        existing = self.ledger.lookup(root)
        info = existing if existing.get("anchored") else self.ledger.anchor(root)
        cur = self.db.execute(
            "INSERT INTO batches(root, leaf_count, sealed_at, tx, height) VALUES(?,?,?,?,?)",
            (root, len(rows), int(time.time()), info.get("tx"), info.get("height")),
        )
        batch_id = cur.lastrowid
        for i, r in enumerate(rows):
            self.db.execute(
                "UPDATE artifacts SET batch_id=?, leaf_index=?, proof=? WHERE id=?",
                (batch_id, i, json.dumps(get_proof(levels, i)), r["id"]),
            )
        self.db.commit()
        return {"batch_id": batch_id, "root": root, "leaf_count": len(rows),
                "tx": info.get("tx"), "height": info.get("height")}

    def bundle(self, artifact_id: str) -> dict | None:
        """Portable proof receipt. Contains hashes only - safe to share."""
        r = self.db.execute("SELECT * FROM artifacts WHERE id=?", (artifact_id,)).fetchone()
        if r is None:
            raise KeyError(f"unknown artifact id {artifact_id}")
        if r["batch_id"] is None:
            return None
        b = self.db.execute("SELECT * FROM batches WHERE id=?", (r["batch_id"],)).fetchone()
        return {
            "artifact_id": r["id"], "filename": r["filename"], "sha256": r["sha256"],
            "leaf": leaf_hash(r["sha256"]), "proof": json.loads(r["proof"]),
            "root": b["root"], "batch_id": b["id"], "tx": b["tx"], "height": b["height"],
        }

    def verify(self, path: str, artifact_id: str | None = None) -> dict:
        if artifact_id is None:  # find the record by content hash
            row = self.db.execute("SELECT id FROM artifacts WHERE sha256=? ORDER BY rowid LIMIT 1",
                                  (sha256_file(path),)).fetchone()
            if row is None:
                return {"verdict": "NOT_FOUND", "checks": [], "artifact_id": None,
                        "note": "No registered artifact has this hash. Never registered, or modified - "
                                "pass --id to compare against a specific artifact."}
            artifact_id = row["id"]
        bundle = self.bundle(artifact_id)
        if bundle is None:
            now = sha256_file(path)
            stored = self.db.execute("SELECT sha256 FROM artifacts WHERE id=?", (artifact_id,)).fetchone()["sha256"]
            return {"verdict": "PENDING", "artifact_id": artifact_id,
                    "checks": [("file hash equals the registered hash", now == stored)],
                    "note": "Registered but not anchored yet - run `seal`."}
        return verify_bundle(path, bundle, self.ledger)

    def list(self) -> list[sqlite3.Row]:
        return self.db.execute("SELECT * FROM artifacts ORDER BY rowid").fetchall()



# 5. CLI

def _make_ledger(args):
    if args.evm:
        return EVMLedger(os.environ["RPC_URL"], os.environ["CONTRACT_ADDRESS"],
                         os.environ["PRIVATE_KEY"], os.environ.get("ABI_PATH", "ArtifactRegistry.abi.json"))
    return LocalLedger(Path(args.data_dir) / "ledger.jsonl")


def _print_verdict(res: dict) -> int:
    icon = {"AUTHENTIC": "PASS", "TAMPERED": "FAIL", "ROOT_NOT_ON_LEDGER": "FAIL",
            "PENDING": "WAIT", "NOT_FOUND": "????"}[res["verdict"]]
    print(f"[{icon}] {res['verdict']}   (artifact {res.get('artifact_id')})")
    for name, ok in res["checks"]:
        print(f"   {'ok ' if ok else 'BAD'}  {name}")
    if res.get("note"):
        print("   " + res["note"])
    return 0 if res["verdict"] == "AUTHENTIC" else 1


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="ECHO artifact integrity")
    p.add_argument("--data-dir", default="echo_integrity_data")
    p.add_argument("--evm", action="store_true", help="anchor on an EVM chain (env: RPC_URL, CONTRACT_ADDRESS, PRIVATE_KEY)")
    sub = p.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("register"); s.add_argument("files", nargs="+")
    sub.add_parser("seal")
    s = sub.add_parser("verify"); s.add_argument("file"); s.add_argument("--id"); s.add_argument("--proof")
    s = sub.add_parser("export"); s.add_argument("--id", required=True); s.add_argument("-o", "--out")
    sub.add_parser("list")
    sub.add_parser("audit")
    args = p.parse_args(argv)

    Path(args.data_dir).mkdir(parents=True, exist_ok=True)
    ledger = _make_ledger(args)
    svc = Integrity(Path(args.data_dir) / "registry.db", ledger)

    if args.cmd == "register":
        for f in args.files:
            r = svc.register(f)
            print(f"registered {r['filename']}\n   id     {r['id']}\n   sha256 {r['sha256']}")
        print("\nnext: `seal` to build the Merkle tree and anchor the root")
    elif args.cmd == "seal":
        r = svc.seal()
        print("nothing pending" if r is None else
              f"sealed batch {r['batch_id']}: {r['leaf_count']} artifact(s)\n   root   {r['root']}\n"
              f"   tx     {r['tx']}\n   height {r['height']}")
    elif args.cmd == "verify":
        if args.proof:
            res = verify_bundle(args.file, json.loads(Path(args.proof).read_text()), ledger)
        else:
            res = svc.verify(args.file, args.id)
        return _print_verdict(res)
    elif args.cmd == "export":
        b = svc.bundle(args.id)
        if b is None:
            print("artifact is not sealed yet - run `seal` first"); return 1
        out = args.out or f"{b['filename']}.proof.json"
        Path(out).write_text(json.dumps(b, indent=2)); print(f"wrote {out}")
    elif args.cmd == "list":
        for r in svc.list():
            state = f"batch {r['batch_id']}" if r["batch_id"] else "pending"
            print(f"{r['id']}  {state:<9} {r['sha256'][:16]}...  {r['filename']}")
    elif args.cmd == "audit":
        if args.evm:
            print("audit is for the local ledger; on-chain history is verified by the chain itself"); return 0
        ok, msg = ledger.validate(); print(("PASS  " if ok else "FAIL  ") + msg); return 0 if ok else 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
