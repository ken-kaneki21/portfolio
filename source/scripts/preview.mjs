import {readFile,writeFile} from 'node:fs/promises';
import path from 'node:path';

const out=path.resolve('dist');
let page=await readFile(path.join(out,'index.html'),'utf8');
const js=page.match(/<script type="module"[^>]*src="([^"]+)"[^>]*><\/script>/);
const css=page.match(/<link rel="stylesheet"[^>]*href="([^"]+)"[^>]*>/);
if (!js||!css) throw new Error('single bundle and stylesheet expected');
const code=await readFile(path.join(out,js[1]),'utf8');
if (/\bimport\.meta|\nexport |\nimport /.test(code)) throw new Error('preview needs a self-contained bundle');
page=page.replace(js[0],'').replace(css[0],'<style>'+await readFile(path.join(out,css[1]),'utf8')+'</style>');
page=page.replace('</body>',()=>'<script>'+code.replace(/<\/script/gi,'<\\/script')+'</script>\n</body>');
await writeFile(path.join(out,'preview.html'),page);
