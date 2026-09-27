const fs = require('fs');
const code = fs.readFileSync('dist/assets/index-BiOLke5t.js', 'utf8');
if (code.includes('Presets')) {
    console.log('Presets found in bundle!');
} else {
    console.log('Presets NOT FOUND in bundle!');
}
if (code.includes('Opacity')) {
    console.log('Opacity found in bundle!');
} else {
    console.log('Opacity NOT FOUND in bundle!');
}
