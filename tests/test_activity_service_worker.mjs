import fs from 'node:fs';
import vm from 'node:vm';
import assert from 'node:assert/strict';
const handlers={},counts={cache:0,fetch:0};
const context={URL,Response,Request,console,Promise,
 self:{location:{origin:'https://example.invalid'},addEventListener:(name,callback)=>handlers[name]=callback},
 caches:{match:async()=>{counts.cache++;return new Response('private stale data')},open:async()=>({put(){counts.cache++}})},
 fetch:async(request,options)=>{counts.fetch++;assert.equal(options.cache,'no-store');return new Response('current authorized data')},
};
vm.createContext(context);vm.runInContext(fs.readFileSync('static/service-worker.js','utf8'),context);
for(const path of ['/activities','/activities?activity=1','/activities/api/summary','/activities/api/photos/1']){
 let result;handlers.fetch({request:new Request('https://example.invalid'+path),respondWith:value=>result=value});
 assert.equal(await (await result).text(),'current authorized data');
}
assert.equal(counts.cache,0,'Sensitive pages, JSON and photos must not enter Cache Storage');
context.fetch=async()=>{throw Error('offline')};
for(const path of ['/activities','/activities/api/photos/1']){
 let result;handlers.fetch({request:new Request('https://example.invalid'+path),respondWith:value=>result=value});
 const response=await result;assert.equal(response.status,503);assert.match(response.headers.get('Cache-Control'),/no-store/);
 assert.doesNotMatch(await response.text(),/stale/);
}
assert.equal(counts.cache,0,'Offline requests must never return a cached previous user response');
console.log('PASS: activity pages, JSON and photos bypass PWA caches online and offline');
