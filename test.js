const React = require('react');
const ReactDOMServer = require('react-dom/server');
const fs = require('fs');

let source = fs.readFileSync('src/workspaces/tools/BrushToolPanel.tsx', 'utf8');
source = source.replace("import { useTool } from '../../context/toolContext';", "const useTool = () => ({ brushColor: [1, 1, 1, 1], setBrushColor: ()=>{}, brushSize: 10, setBrushSize: ()=>{} });");
source = source.replace("import './ToolPanels.css';", "");
fs.writeFileSync('temp.tsx', source);

require('esbuild').buildSync({
  entryPoints: ['temp.tsx'],
  bundle: true,
  outfile: 'out.js',
  format: 'cjs',
  external: ['react']
});

const BrushToolPanel = require('./out.js').default;
try {
  const html = ReactDOMServer.renderToString(React.createElement(BrushToolPanel));
  console.log('SUCCESS', html.length);
} catch (e) {
  console.error('ERROR', e);
}
