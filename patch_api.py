import os

with open('src/api/toolsApi.ts', 'r', encoding='utf-8') as f:
    text = f.read()

# I will append the editor tool endpoints at the end of the file.
append_text = '''
// Editor Tools

export const editorToolsApi = {
  brush: (points: {x:number, y:number}[], size: number, color?: number[], opacity?: number) =>
    post('/editor/brush', { points, size, color, opacity }),
  eraser: (points: {x:number, y:number}[], size: number) =>
    post('/editor/eraser', { points, size }),
};
'''

if "editorToolsApi" not in text:
    with open('src/api/toolsApi.ts', 'a', encoding='utf-8') as f:
        f.write(append_text)
