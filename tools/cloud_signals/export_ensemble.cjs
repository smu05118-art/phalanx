/* UI와 동일한 계산기를 사용해 다른 파이프라인에서 읽을 정규화 결과를 저장한다. */
const fs=require('node:fs');
const path=require('node:path');
const engine=require('../../ui/cloud_signals.js');
const root=path.resolve(__dirname,'../..');
const ledger=JSON.parse(fs.readFileSync(path.join(root,'data/cloud_signals/ledger.json'),'utf8'));
if(ledger.schema!=='cloud_signals/1')throw Error('원장 스키마 불일치');
const data={schema:'cloud_ensemble/1',asof:ledger.updated,tracking_started:ledger.tracking_started,
  method:'규칙 기반 관측 방향. 예측 확률 아님. 2축/40% 이상, 180일 제한, 90일 반감기.',weights:engine.WEIGHTS,
  companies:Object.keys(ledger.providers).sort().map(id=>engine.ensemble(ledger.signals,id,ledger.updated))};
const out=path.join(root,'data/cloud_signals/ensemble.json'),tmp=out+'.tmp';
fs.writeFileSync(tmp,JSON.stringify(data)+'\n');fs.renameSync(tmp,out);
console.log(`${data.companies.length}개 업체 · ${data.companies.filter(x=>x.score!==null).length}개 점수 산출`);
