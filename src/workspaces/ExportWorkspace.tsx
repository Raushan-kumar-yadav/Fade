import { useState, useRef, useEffect, useCallback } from 'react'
import './ExportWorkspace.css'
import { exportApi, type ExportProgress } from '../api/toolsApi'

interface CompMeta {
  compId: string; name: string; kind: string
  isRoot: boolean; isHidden: boolean; isDefault: boolean
  trackCount: number; clipCount: number
  width: number; height: number; fps: number; totalFrames: number
}
interface CompJobProgress {
  done: boolean; error: string | null; path: string | null
  percent: number; label: string; done_pages: number; total: number; kind: string
}
interface Format { id: string; label: string; icon: string; desc: string; w: number; h: number; ext: string }

const FORMATS: Format[] = [
  { id: 'mp4-1080', label: 'MP4 1080p', icon: '🎬', desc: 'H.264, AAC · 1920×1080', w: 1920, h: 1080, ext: 'mp4' },
  { id: 'mp4-4k',   label: 'MP4 4K',   icon: '🎬', desc: 'H.264 · 3840×2160', w: 3840, h: 2160, ext: 'mp4' },
  { id: 'mp4-720',  label: 'MP4 720p', icon: '🎬', desc: 'H.264 · 1280×720', w: 1280, h:  720, ext: 'mp4' },
  { id: 'shorts', label: 'YT Shorts',icon: '📱', desc: '1080×1920, 60s max', w: 1080, h: 1920, ext: 'mp4' },
  { id: 'reels', label: 'IG Reels', icon: '📱', desc: '1080×1920, AAC', w: 1080, h: 1920, ext: 'mp4' },
  { id: 'webm', label: 'WebM VP9', icon: '🌐', desc: 'Open format · 1920×1080',   w: 1920, h: 1080, ext: 'webm' },
  { id: 'gif', label: 'GIF',      icon: '🎭', desc: 'Animated · 854×480', w:  854, h:  480, ext: 'gif' },
] 
const FPS_OPTIONS    = ['24','25','30','50','60']
const PRESET_OPTIONS = ['ultrafast','superfast','veryfast','faster','fast','medium','slow','slower','veryslow']
const AUDIO_SR = [{ v:'44100', l:'44.1 kHz' },{ v:'48000', l:'48 kHz' }]
const AUDIO_CH = [{ v:'2', l:'Stereo' },{ v:'6', l:'5.1 Surround' }]
const AUDIO_BR = ['96k','128k','192k','256k','320k']
const KIND_ICON: Record<string,string> = { video:'🎬', image:'🖼️', pdf:'📄' }
const KIND_LABEL: Record<string,string> = { video:'Video Comp', image:'Image Comp', pdf:'PDF Document' }

function estimatedMB(w:number,h:number,fpsVal:number,durSec:number,kbps:number):string{
  return ((kbps*durSec)/8/1024).toFixed(0)+' MB'
}

export default function ExportWorkspace() {
  const port = (window as any).__FADE_PORT__ ?? 8000
  const [comps,setComps] = useState<CompMeta[]>([])
  const [selectedCompId,setSelectedCompId] = useState<string|null>(null)
  const [selected,setSelected] = useState<string>('mp4-1080')
  const [fps,setFps] = useState<string>('30')
  const [outputPath,setOutputPath] = useState<string>('fade_export.mp4')
  const [compJobId,setCompJobId] = useState<string|null>(null)
  const [compProgress,setCompProgress] = useState<CompJobProgress|null>(null)
  const compPollRef = useRef<ReturnType<typeof setInterval>|null>(null)
  const [jobId,setJobId] = useState<string|null>(null)
  const [progress,setProgress] = useState<ExportProgress|null>(null)
  const [webcompPhase,setWebcompPhase] = useState<{active:boolean;done:number;total:number}|null>(null)
  const [qualityMode,setQualityMode] = useState<'crf'|'bitrate'>('crf')
  const [crf,setCrf] = useState<number>(22)
  const [videoBr,setVideoBr] = useState<string>('8')
  const [preset,setPreset] = useState<string>('medium')
  const [audioBr,setAudioBr] = useState<string>('192k')
  const [audioSR,setAudioSR] = useState<string>('48000')
  const [audioCh,setAudioCh] = useState<string>('2')
  const pollRef = useRef<ReturnType<typeof setInterval>|null>(null)
  const cleanupRef = useRef<(()=>void)|null>(null)
  const wcCleanup = useRef<(()=>void)|null>(null)
  const fmt = FORMATS.find(f=>f.id===selected)!

  // Integrity state  
  const [integrityEnabled, setIntegrityEnabled] = useState(false)
  type IState = {phase:'idle'}|{phase:'running'}|{phase:'done';artifactId:string;tx:string|null;wmPath:string|null}|{phase:'error';msg:string}
  const [iState, setIState] = useState<IState>({phase:'idle'})

  const runIntegrity = useCallback(async (filePath: string) => {
    setIState({phase:'running'})
    try {
      const r = await fetch(`http://127.0.0.1:${port}/integrity/register`, {
        method: 'POST',
        headers: {'Content-Type':'application/json'},
        body: JSON.stringify({ video_path: filePath }),
      })
      if (!r.ok) { const d=await r.json().catch(()=>({})); setIState({phase:'error',msg:d.detail??`Server error ${r.status}`}); return }
      const d = await r.json()
      setIState({ phase:'done', artifactId: d.artifact_id, tx: d.batch?.tx??null, wmPath: d.watermarked_output_path??null })
    } catch(e:any) {
      setIState({phase:'error', msg: e.message??'Registration failed'})
    }
  }, [port])
 

 
  useEffect(() => {
    if (!integrityEnabled) return
    // Check both export paths (comp and video)
    const filePath = compProgress?.path ?? progress?.path ?? null
    if (!filePath) return
    const done = compProgress?.done ?? progress?.done ?? false
    const hasErr = !!(compProgress?.error ?? progress?.error)
    if (done && !hasErr && iState.phase === 'idle') {
      runIntegrity(filePath)
    }
  }, [compProgress?.done, compProgress?.path, progress?.done, progress?.path, integrityEnabled, iState.phase, runIntegrity])


  const fetchComps = async () => {
    try {
      const r = await fetch(`http://127.0.0.1:${port}/comps`)
      const d = await r.json()
      const list: CompMeta[] = (d.comps??[]).filter((c:CompMeta)=>!c.isHidden)
      setComps(list)
      setSelectedCompId(prev=>{
        if(prev) return prev
        const root=list.find(c=>c.isRoot)
        return root?.compId??list[0]?.compId??null
      })
    } catch {}
  }
  useEffect(()=>{fetchComps()},[])
  useEffect(()=>{
    const h=()=>fetchComps()
    window.addEventListener('fade:library-changed',h)
    window.addEventListener('fade:tracks-changed',h)
    return()=>{window.removeEventListener('fade:library-changed',h);window.removeEventListener('fade:tracks-changed',h)}
  },[])

  const selectedComp = comps.find(c=>c.compId===selectedCompId)??null
  const compKind = selectedComp?.kind??'video'

  useEffect(()=>{
    const api=(window as any).electronAPI
    const ext=compKind==='image'?'png':compKind==='pdf'?'pdf':fmt.ext
    const base=selectedComp?selectedComp.name.replace(/[\\/:*?"<>|]/g,'_'):'fade_export'
    if(api?.getAppPath){
      const folder=compKind==='image'?'pictures':compKind==='pdf'?'documents':'videos'
      api.getAppPath(folder).then((dir:string|null)=>{
        const sep=dir?.includes('/')?'/':'\\'
        setOutputPath(dir?`${dir}${sep}${base}.${ext}`:`${base}.${ext}`)
      }).catch(()=>setOutputPath(`${base}.${ext}`))
    } else { setOutputPath(`${base}.${ext}`) }
  },[selectedCompId,compKind,fmt.ext])

  const [durSec,setDurSec]=useState<number>(10)
  useEffect(()=>{
    const api=(window as any).electronAPI
    if(!api) return
    api.getPort?.().then(async(p:number|null)=>{
      if(!p) return
      try{const r=await fetch(`http://127.0.0.1:${p}/playback/state`);const s=await r.json();if(s.totalFrames)setDurSec(s.totalFrames/parseFloat(fps))}catch{}
    })
  },[fps])

  const stopPoll=()=>{if(pollRef.current){clearInterval(pollRef.current);pollRef.current=null}}
  const stopCompPoll=()=>{if(compPollRef.current){clearInterval(compPollRef.current);compPollRef.current=null}}
  useEffect(()=>()=>{stopPoll();stopCompPoll();cleanupRef.current?.();wcCleanup.current?.()},[])

  async function startCompExport(){
    if(!selectedComp) return
    const api=(window as any).electronAPI

    if(api?.captureImage && compKind==='image'){
      setCompProgress({done:false,error:null,path:null,percent:0,label:'Capturing frame via C++ engine…',done_pages:0,total:1,kind:'image'})
      try{
        const result = await api.captureImage({
          compId: selectedComp.compId,
          width: selectedComp.width ?? fmt.w,
          height: selectedComp.height ?? fmt.h,
          fps: parseFloat(fps),
          outputPath,
        })
        if(result.ok){
          setCompProgress({done:true,error:null,path:result.path??outputPath,percent:100,label:'Done',done_pages:1,total:1,kind:'image'})
        } else {
          setCompProgress(p=>({...p!,error:result.error??'Export failed',done:true}))
        }
      }catch(e:any){setCompProgress(p=>({...p!,error:e.message??'Unknown error',done:true}))}
      return
    }

    if(api?.capturePdf && compKind==='pdf'){
      setCompProgress({done:false,error:null,path:null,percent:0,label:'Fetching pages…',done_pages:0,total:1,kind:'pdf'})
      try{
        const pr = await fetch(`http://127.0.0.1:${port}/comps/${selectedComp.compId}/pdf-pages`)
        if(!pr.ok) throw new Error('Failed to fetch PDF pages')
        const pdata = await pr.json()
        const pages:(Array<{compId:string;width:number;height:number}>) = pdata.pages ?? []
        if(!pages.length) throw new Error('PDF has no pages')
        setCompProgress(p=>({...p!,label:`Capturing ${pages.length} page(s) via C++ engine…`,total:pages.length}))
        const result = await api.capturePdf({pdfCompId:selectedComp.compId,pages,outputPath,fps:parseFloat(fps)})
        if(result.ok){
          setCompProgress({done:true,error:null,path:outputPath,percent:100,label:'Done',done_pages:pages.length,total:pages.length,kind:'pdf'})
        } else {
          setCompProgress(p=>({...p!,error:result.error??'PDF assembly failed',done:true}))
        }
      }catch(e:any){setCompProgress(p=>({...p!,error:e.message??'Unknown error',done:true}))}
      return
    }

    // Fallback: Python-only path (web/no-electron mode)
    setCompProgress({done:false,error:null,path:null,percent:0,label:'Starting…',done_pages:0,total:1,kind:compKind})
    setCompJobId(null);stopCompPoll()
    try{
      const body:any={compId:selectedComp.compId,outputPath,width:fmt.w,height:fmt.h,fps:parseFloat(fps),
        codec:'auto',videoBitrate:`${videoBr}M`,crf:qualityMode==='crf'?crf:-1,preset,
        audioBitrate:audioBr,audioSampleRate:parseInt(audioSR),audioChannels:parseInt(audioCh)}
      const r=await fetch(`http://127.0.0.1:${port}/export/comp`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)})
      if(!r.ok){const err=await r.json();setCompProgress(p=>({...p!,error:err.detail??'Export failed',done:true}));return}
      const {jobId:jid}=await r.json();setCompJobId(jid)
      // Notify ExportProgressOverlay so integrity section appears on completion
      window.dispatchEvent(new CustomEvent('fade:export-started', { detail: { jobId: jid } }))
      compPollRef.current=setInterval(async()=>{
        try{
          const pr=await fetch(`http://127.0.0.1:${port}/export/comp/progress/${jid}`)
          if(!pr.ok) return
          const pdata:CompJobProgress=await pr.json();setCompProgress(pdata);if(pdata.done)stopCompPoll()
        }catch{stopCompPoll()}
      },400)
    }catch(e:any){setCompProgress(p=>({...p!,error:e.message??'Unknown error',done:true}))}
  }

  async function cancelCompExport(){
    if(compJobId) await fetch(`http://127.0.0.1:${port}/export/comp/cancel/${compJobId}`,{method:'POST'}).catch(()=>{})
    stopCompPoll();setCompJobId(null);setCompProgress(null)
  }

  async function startExport(){
    const api=(window as any).electronAPI
    if(compKind==='image'||compKind==='pdf'){await startCompExport();return}
    if(api?.startExport&&api?.onExportProgress){
      setJobId('native');setProgress({jobId:'native',frame:0,total:0,percent:0,done:false,error:null,path:null});setWebcompPhase(null)
      // Notify ExportProgressOverlay
      window.dispatchEvent(new CustomEvent('fade:export-started', { detail: { jobId: 'native' } }))
      cleanupRef.current?.();wcCleanup.current?.()
      if(api.onExportWebcompPhase) wcCleanup.current=api.onExportWebcompPhase((p:{active:boolean;done:number;total:number})=>setWebcompPhase(p.total>0?p:null))
      cleanupRef.current=api.onExportProgress((p:{frame:number;total:number;done:boolean;error:string;status?:string})=>{
        const pct=p.total>0?Math.round((p.frame/p.total)*100):0
        setProgress({jobId:'native',frame:p.frame,total:p.total,percent:pct,done:p.done,error:p.error||null,path:p.done&&!p.error?outputPath:null,status:p.status})
        if(p.done){cleanupRef.current?.();cleanupRef.current=null;wcCleanup.current?.();wcCleanup.current=null;setJobId(null);setWebcompPhase(null)}
      })
      api.startExport({outputPath,width:fmt.w,height:fmt.h,fps:parseFloat(fps),codec:'auto',videoBitrate:`${videoBr}M`,crf:qualityMode==='crf'?crf:-1,preset,audioBitrate:audioBr,audioSampleRate:parseInt(audioSR),audioChannels:parseInt(audioCh)})
      return
    }
    try{
      const res=await exportApi.start({outputPath,width:fmt.w,height:fmt.h,fps:parseFloat(fps),formatId:selected,videoBitrate:`${videoBr}M`,crf:qualityMode==='crf'?crf:-1,preset,audioBitrate:audioBr,audioSampleRate:parseInt(audioSR),audioChannels:parseInt(audioCh)})
      setJobId(res.jobId);setProgress({jobId:res.jobId,frame:0,total:res.total,percent:0,done:false,error:null,path:null})
       window.dispatchEvent(new CustomEvent('fade:export-started', { detail: { jobId: res.jobId } }))
      pollRef.current=setInterval(async()=>{try{const p=await exportApi.progress(res.jobId);setProgress(p);if(p.done)stopPoll()}catch{stopPoll()}},500)
    }catch(err:any){alert(`Export failed: ${err.message}`)}
  }

  async function cancelExport(){
    const api=(window as any).electronAPI
    if(jobId==='native'){api?.cancelExport();cleanupRef.current?.();cleanupRef.current=null;wcCleanup.current?.();wcCleanup.current=null}
    else if(jobId){await exportApi.cancel(jobId);stopPoll()}
    setProgress(null);setJobId(null);setWebcompPhase(null)
  }

  function browseOutput(){
    const api=(window as any).electronAPI
    if(api?.showSaveDialog){
      const extMap:Record<string,string[]>={image:['png'],pdf:['pdf'],video:[fmt.ext]}
      const exts=extMap[compKind]??[fmt.ext]
      api.showSaveDialog({filters:[{name:'Output',extensions:exts}],defaultPath:outputPath}).then((p:string|undefined)=>{if(p)setOutputPath(p)})
    }
  }

  const compExporting=!!compJobId&&!compProgress?.done
  const videoExporting=!!jobId&&!progress?.done
  const exporting=compExporting||videoExporting
  const pct=compProgress?.percent??progress?.percent??0
  const wcPct=webcompPhase&&webcompPhase.total>0?Math.round((webcompPhase.done/webcompPhase.total)*100):0
  const estSize=estimatedMB(fmt.w,fmt.h,parseFloat(fps),durSec,qualityMode==='crf'?(3000+(28-crf)*400):parseFloat(videoBr)*1000)
  const showVideoSettings=compKind==='video'

  return (
    <div className="export-ws">
      <div className="export-ws__left">
        <h2>Composition {comps.length > 0 ? `(${comps.length})` : ''}</h2>
        <div className="export-comp-hint">Click a composition to select it for export</div>
        <div className="export-comp-list">
          {comps.length===0&&<div className="export-comp-empty">No compositions — open a project first</div>}
          {comps.map(c=>{
            const isActive = selectedCompId===c.compId
            return (
              <div key={c.compId}
                className={`export-comp-item${isActive?' export-comp-item--active':''}`}
                title={`Export this ${KIND_LABEL[c.kind]??'composition'}`}
                onClick={()=>!exporting&&setSelectedCompId(c.compId)}>
                {/* Radio circle */}
                <div className="export-comp-radio">
                  <div className="export-comp-radio-dot" />
                </div>
                <span className="export-comp-item__icon">{KIND_ICON[c.kind]??'🎬'}</span>
                <div className="export-comp-item__info">
                  <div className="export-comp-item__name">{c.name}{c.isRoot?' (Root)':''}</div>
                  <div className="export-comp-item__meta">{KIND_LABEL[c.kind]??c.kind} · {c.clipCount} clip{c.clipCount!==1?'s':''}</div>
                </div>
                {isActive && <span className="export-comp-badge">EXPORT</span>}
              </div>
            )
          })}
        </div>

        {showVideoSettings&&(<>
          <h2 style={{marginTop:20}}>Output Format</h2>
          <div className="export-formats">
            {FORMATS.map(f=>(
              <div key={f.id} className={`export-fmt${selected===f.id?' export-fmt--active':''}`} onClick={()=>!exporting&&setSelected(f.id)}>
                <span className="export-fmt__icon">{f.icon}</span>
                <div><div className="export-fmt__label">{f.label}</div><div className="export-fmt__desc">{f.desc}</div></div>
                {selected===f.id&&<span className="export-fmt__check">✓</span>}
              </div>
            ))}
          </div>
        </>)}

        {compKind==='image'&&selectedComp&&(
          <div className="export-comp-info-card export-comp-info-card--image">
            <div className="export-comp-info-card__icon">🖼️</div>
            <div>
              <div className="export-comp-info-card__title">{selectedComp.name}</div>
              <div className="export-comp-info-card__body">Exports as <strong>PNG</strong> · {selectedComp.width}×{selectedComp.height}px</div>
            </div>
          </div>
        )}
        {compKind==='pdf'&&selectedComp&&(
          <div className="export-comp-info-card export-comp-info-card--pdf">
            <div className="export-comp-info-card__icon">📄</div>
            <div>
              <div className="export-comp-info-card__title">{selectedComp.name}</div>
              <div className="export-comp-info-card__body">Exports as <strong>PDF</strong> — each page rendered at {selectedComp.width}×{selectedComp.height}px and combined into a single document.</div>
            </div>
          </div>
        )}
      </div>

      <div className="export-ws__right">
        <h2>Export Settings</h2>
        <div className="export-props">
          {showVideoSettings&&(
            <div className="export-prop-row">
              <div className="export-prop"><label>Resolution</label><div className="export-prop__value">{fmt.w} × {fmt.h}</div></div>
              <div className="export-prop"><label>Frame Rate</label>
                <select value={fps} onChange={e=>setFps(e.target.value)} disabled={exporting}>
                  {FPS_OPTIONS.map(r=><option key={r} value={r}>{r} fps</option>)}
                </select>
              </div>
            </div>
          )}
          {showVideoSettings&&(
            <div className="export-section">
              <div className="export-section__title">Video Quality</div>
              <div className="export-toggle-row">
                <button className={`export-mode-btn${qualityMode==='crf'?' active':''}`} onClick={()=>setQualityMode('crf')} disabled={exporting}>CRF (Quality)</button>
                <button className={`export-mode-btn${qualityMode==='bitrate'?' active':''}`} onClick={()=>setQualityMode('bitrate')} disabled={exporting}>Bitrate</button>
              </div>
              {qualityMode==='crf'?(
                <div className="export-prop">
                  <label>Quality · CRF {crf} {crf<=18?'(Lossless)':crf<=23?'(High)':crf<=28?'(Medium)':'(Low)'}</label>
                  <input type="range" min={12} max={35} value={crf} onChange={e=>setCrf(parseInt(e.target.value))} disabled={exporting}/>
                  <div className="export-slider-labels"><span>Best</span><span>Fastest</span></div>
                </div>
              ):(
                <div className="export-prop">
                  <label>Video Bitrate · {videoBr} Mbps</label>
                  <input type="range" min={2} max={40} value={parseFloat(videoBr)} onChange={e=>setVideoBr(e.target.value)} disabled={exporting}/>
                  <div className="export-slider-labels"><span>2 Mbps</span><span>40 Mbps</span></div>
                </div>
              )}
              <div className="export-prop"><label>Encoder Preset</label>
                <select value={preset} onChange={e=>setPreset(e.target.value)} disabled={exporting}>
                  {PRESET_OPTIONS.map(p=><option key={p} value={p}>{p}</option>)}
                </select>
              </div>
            </div>
          )}
          {showVideoSettings&&(
            <div className="export-section">
              <div className="export-section__title">Audio</div>
              <div className="export-prop-row">
                <div className="export-prop"><label>Sample Rate</label>
                  <select value={audioSR} onChange={e=>setAudioSR(e.target.value)} disabled={exporting}>
                    {AUDIO_SR.map(o=><option key={o.v} value={o.v}>{o.l}</option>)}
                  </select>
                </div>
                <div className="export-prop"><label>Channels</label>
                  <select value={audioCh} onChange={e=>setAudioCh(e.target.value)} disabled={exporting}>
                    {AUDIO_CH.map(o=><option key={o.v} value={o.v}>{o.l}</option>)}
                  </select>
                </div>
                <div className="export-prop"><label>Bitrate</label>
                  <select value={audioBr} onChange={e=>setAudioBr(e.target.value)} disabled={exporting}>
                    {AUDIO_BR.map(b=><option key={b} value={b}>{b}</option>)}
                  </select>
                </div>
              </div>
            </div>
          )}
          <div className="export-prop"><label>Output Path</label>
            <div className="export-path">
              <input value={outputPath} onChange={e=>setOutputPath(e.target.value)} disabled={exporting} placeholder="Select output path…"/>
              <button onClick={browseOutput} disabled={exporting}>Browse</button>
            </div>
          </div>
          {showVideoSettings&&(
            <div className="export-estimate">
              <span>Estimated size:</span><strong>{estSize}</strong><span>· ~{Math.round(durSec)}s at {fps} fps</span>
            </div>
          )}
        </div>

        {webcompPhase&&webcompPhase.total>0&&(
          <div className="export-progress export-progress--phase">
            <div className="export-progress__label">
              <span className="export-phase-badge">Preparing overlays…</span>
              <span>{wcPct}% ({webcompPhase.done}/{webcompPhase.total} frames)</span>
            </div>
            <div className="export-progress__bar"><div className="export-progress__fill export-progress__fill--webcomp" style={{width:`${wcPct}%`}}/></div>
          </div>
        )}

        {compProgress&&(
          <div className="export-progress">
            <div className="export-progress__label">
              {compProgress.done&&!compProgress.error
                ?<span className="export-done">✅ Export complete</span>
                :compProgress.error
                  ?<span className="export-error">❌ {compProgress.error}</span>
                  :compKind==='pdf'
                    ?<span>{compProgress.label}{compProgress.total>1&&` (${compProgress.done_pages}/${compProgress.total} pages)`}</span>
                    :<span>{compProgress.label}</span>
              }
            </div>
            <div className="export-progress__bar"><div className="export-progress__fill" style={{width:`${compProgress.percent}%`}}/></div>
            {compProgress.done&&!compProgress.error&&compProgress.path&&<div className="export-done-path">📁 {compProgress.path}</div>}
          </div>
        )}

        {progress&&!compProgress&&(
          <div className="export-progress">
            {!webcompPhase?.active&&(
              <div className="export-progress__label">
                {progress.done&&!progress.error?<span className="export-done">✅ Export complete</span>
                  :progress.error?<span className="export-error">❌ {progress.error}</span>
                  :progress.status==='audio'?<span className="export-phase-badge export-phase-badge--audio">🎵 Muxing audio…</span>
                  :<span>Encoding… {pct}% · frame {progress.frame} / {progress.total}</span>}
              </div>
            )}
            <div className="export-progress__bar"><div className="export-progress__fill" style={{width:`${pct}%`}}/></div>
            {progress.done&&!progress.error&&progress.path&&<div className="export-done-path">📁 {progress.path}</div>}
          </div>
        )}

        {/*   Integrity checkbox   */}
        {!exporting && (
          <label className="export-integrity-toggle">
            <div className={"export-integrity-check" + (integrityEnabled ? " export-integrity-check--on" : "")}
              onClick={() => { setIntegrityEnabled(v => !v); setIState({phase:'idle'}) }}>
              {integrityEnabled && <span>&#x2713;</span>}
            </div>
            <div className="export-integrity-toggle__text">
              <span className="export-integrity-toggle__label">&#x1F512; Register for Integrity Verification</span>
              <span className="export-integrity-toggle__sub">Embeds invisible watermark &bull; anchors hash to ledger</span>
            </div>
          </label>
        )}
        

        <div className="export-actions">
          {exporting
            ?<button className="export-btn export-btn--cancel" onClick={compExporting?cancelCompExport:cancelExport}>Cancel</button>
            :<button className="export-btn export-btn--primary" onClick={() => { setIState({phase:'idle'}); startExport() }} disabled={!selectedComp}>
              {compKind==='image'?'Export PNG':compKind==='pdf'?'Export PDF':'Export Video'}
            </button>
          }
        </div>

        {/*   Inline integrity status   */}
        {integrityEnabled && iState.phase !== 'idle' && (
          <div className="export-integrity-status">
            {iState.phase === 'running' && (
              <div className="export-integrity-status__running">
                <span className="export-integrity-spin" />
                Hashing &bull; Fingerprinting &bull; Watermarking&hellip;
              </div>
            )}
            {iState.phase === 'done' && (
              <div className="export-integrity-status__done">
                <div className="export-integrity-status__ok">&#x2705; Registered on ledger</div>
                <div className="export-integrity-status__row">
                  <span>Artifact</span>
                  <code>{iState.artifactId}</code>
                </div>
                {iState.tx && (
                  <div className="export-integrity-status__row">
                    <span>TX</span>
                    <code title={iState.tx}>{iState.tx.slice(0,18)}...</code>
                  </div>
                )}
                <div className="export-integrity-status__btns">
                  <button className="export-integrity-status__btn"
                    onClick={() => {
                      const a = document.createElement('a')
                      a.href = `http://127.0.0.1:${port}/integrity/proof/${iState.artifactId}`
                      a.download = `${iState.artifactId}.proof.json`
                      a.click()
                    }}>
                    &#x2B07; Proof JSON
                  </button>
                  {iState.wmPath && (
                    <button className="export-integrity-status__btn export-integrity-status__btn--wm"
                      onClick={() => (window as any).electronAPI?.showItemInFolder?.(iState.wmPath)}
                      title={iState.wmPath}>
                      &#x1F4C2; Watermarked Copy
                    </button>
                  )}
                </div>
              </div>
            )}
            {iState.phase === 'error' && (
              <div className="export-integrity-status__error">
                <span>&#x26A0;&#xFE0F; {iState.msg}</span>
                <button className="export-integrity-status__retry"
                  onClick={() => {
                    const fp = compProgress?.path ?? progress?.path
                    if (fp) runIntegrity(fp)
                  }}>Retry</button>
              </div>
            )}
          </div>
        )}
        
      </div>
    </div>
  )
}