const assert=require('node:assert/strict');
const fs=require('node:fs/promises');
const {createServer}=require('node:http');
const path=require('node:path');
const url=require('node:url');
const {chromium}=require('playwright');
const root=path.resolve(process.argv[2]);
const out=path.resolve(process.argv[3]);
const chrome=process.argv[4];
const mount='/portfolio/';
const mime={'.html':'text/html','.js':'text/javascript','.css':'text/css','.json':'application/json','.pdf':'application/pdf','.txt':'text/plain'};
const requests=[];
const fileFor=pathname=>{
 if(!pathname.startsWith(mount)) throw new Error('wrong deployment base');
 const rel=decodeURIComponent(pathname.slice(mount.length))||'index.html';
 const full=path.resolve(root,rel);
 if (!full.startsWith(root+path.sep)) throw new Error('nonlocal path');
 return full;
};
async function serve(pathname) {
 const file=fileFor(pathname);
 return {body:await fs.readFile(file),contentType:mime[path.extname(file)]||'application/octet-stream'};
}
async function run() {
 await fs.mkdir(out,{recursive:true});
 const server=createServer((req,res)=>{serve(new URL(req.url,'http://localhost').pathname)
   .then(r=>res.writeHead(200,{'content-type':r.contentType}).end(r.body),()=>res.writeHead(404).end());});
 await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
 const origin='http://127.0.0.1:'+server.address().port;
 const browser=await chromium.launch({executablePath:chrome,headless:true,args:['--disable-background-networking']});
 let intercepted=false;
 const sizes=[];
 try{
  for (const viewport of [{width:1440,height:920},{width:390,height:844},{width:320,height:800}]) {
   const context=await browser.newContext({viewport,reducedMotion:'reduce',acceptDownloads:true,serviceWorkers:'block'});
   await context.route('**/*',async req=>{
      const u=new URL(req.request().url());
      if(u.origin!==origin){requests.push(u.origin);return req.abort();}
      if(!intercepted)return req.continue();
      try{return req.fulfill({status:200,...await serve(u.pathname)});}
      catch{return req.fulfill({status:404,body:'Not found'});}
   });
   let page=await context.newPage();const errors=[];
   const watch=p=>p.on('pageerror',e=>errors.push(e.message));
   watch(page);
   try {await page.goto(origin+mount);}
   catch(e){
    if(!String(e).includes('ERR_NETWORK_ACCESS_DENIED'))throw e;
    intercepted=true;
    await page.close();
    page=await context.newPage();
    watch(page);
    await page.goto(origin+mount);
   }
   await page.getByRole('heading',{level:1}).waitFor();
   assert.match(await page.title(),/Saurabh/);
   await page.keyboard.press('Tab');
   assert.equal(await page.evaluate(()=>document.activeElement.textContent),'Skip to content');
   assert.notEqual(await page.evaluate(()=>getComputedStyle(document.activeElement).outlineStyle),'none');
   await page.keyboard.press('Enter');
   assert.match(page.url(),/#main$/);
   const nav=page.getByRole('navigation',{name:'Main navigation'});
   await nav.getByRole('link',{name:'Projects'}).click();
   assert.match(page.url(),/#work$/);
   await nav.getByRole('link',{name:'Experience'}).click();
   assert.match(page.url(),/#experience$/);
   const links=await page.locator('a').evaluateAll(nodes=>nodes.map(n=>n.getAttribute('href')));
   const publicSourceLinks = new Set([
     'https://github.com/ken-kaneki21/job-portal',
     'https://github.com/ken-kaneki21/EvidenceWorks',
     'https://github.com/ken-kaneki21/healthcare-claims-platform'
   ]);
   assert.deepEqual(new Set(links.filter(href=>href.startsWith('https://'))),publicSourceLinks);
   for(const href of links){
     if(href.startsWith('#'))assert.equal(await page.locator(href).count(),1,href);
     else if(!publicSourceLinks.has(href)) await serve(new URL(href,origin+mount).pathname);
   }
   for(const name of ['Healthcare Claims Platform','Job Intelligence','EvidenceWorks'])
     assert.equal(await page.getByRole('heading',{name,exact:true}).count(),1);
   const dl=page.waitForEvent('download');
   await nav.getByRole('link',{name:'Resume PDF'}).click();
   assert.equal((await dl).suggestedFilename(),'saurabh-public-resume.pdf');
   await page.evaluate(()=>window.scrollTo(0,0));
   const overflow=await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth);
   assert.equal(overflow,false,viewport.width+' horizontal overflow');
   assert.deepEqual(errors,[]);
   assert.equal(await page.evaluate(()=>getComputedStyle(document.documentElement).scrollBehavior),'auto');
   await page.screenshot({path:path.join(out,'portfolio-'+viewport.width+'.png'),fullPage:true,animations:'disabled'});
   sizes.push({viewport,links:links.length,overflow,keyboard_focus:true,resume_download:true});
   await context.close();
  }
  assert.deepEqual(requests,[]);
  const previewContext=await browser.newContext();
  const page=await previewContext.newPage();
  let filePreview='blocked';
  try{
   await page.goto(url.pathToFileURL(path.join(root,'preview.html')).href);
   await page.getByRole('heading',{level:1}).waitFor({timeout:3000});
   filePreview='PASS';
  }catch(e){filePreview=String(e).split('\n')[0];}
  await previewContext.close();
  const report={status:'PASS',mount,viewport_checks:sizes,transport:intercepted?'playwright-fulfilled-static-origin':'loopback-http',
      file_preview:filePreview,chrome:browser.version(),external_requests:requests.length};
  await fs.writeFile(path.join(out,'browser-portfolio.json'),JSON.stringify(report,null,2)+'\n');
  console.log(JSON.stringify(report));
 }finally{await browser.close();await new Promise(resolve=>server.close(resolve));}
}
run().catch(e=>{console.error(e.stack);process.exitCode=1;});
