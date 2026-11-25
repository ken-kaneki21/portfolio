export type CaseStudy = {
  source?: string;
  id: string; title: string; category: string; lead: string;
  facts: { label: string; value: string }[];
  sections: { label: string; text: string }[];
  evidence: { name: string; path: string }[];
};

export const projects: CaseStudy[] = [
  {
    id:'healthcare', source:'https://github.com/ken-kaneki21/healthcare-claims-platform', title:'Healthcare Claims Platform', category:'Finance & LLM guardrails',
    lead:'An authenticated claims assistant that routes requests to independently checked financial tools.',
    facts:[{label:'Frozen cases',value:'11'},{label:'SQL-matched answers',value:'3'},{label:'Live Qwen requests',value:'2'}],
    sections:[
      {label:'Problem and contribution',text:'Analysts need financial answers that can be reconciled. I implemented the synthetic evaluation harness, independent SQL oracle comparisons and tests for authenticated access and unsupported requests.'},
      {label:'Architecture and scope',text:'Signed demo authentication gates a local Python service. A small Qwen model can propose a route. Policy checks and deterministic financial tools govern the final answer. The seeded ledger has 100 synthetic members across three tenants.'},
      {label:'Baseline and result',text:'The deterministic financial oracle is the comparison baseline. All 11 authored HTTP checks met expectations. Three successful financial cases matched SQL. One actual Qwen response selected a financial route and another proposal was stopped by policy.'},
      {label:'Pretrained Qwen serving',text:'A separate loopback HTTP streaming benchmark used Qwen 2.5 1.5B Instruct on one CPU slot. Across eight requests per arm, median first-token latency rose from 155 ms at one client to 1,122 ms at two. Aggregate throughput stayed near 29 tokens/s as the second client queued.'},
      {label:'Limitations',text:'The integration evidence covers local demo authentication and two live provider calls. The separate serving run used synthetic prompts on a Ryzen 5 5600H and measured local timing. Production capacity, model quality and broader identity coverage remain unverified.'}
    ],
    evidence:[{name:'Accepted application report',path:'evidence/healthcare-acceptance.json'},{name:'Qwen serving report',path:'evidence/qwen-http-benchmark.json'}]
  },
  {
    id:'job-intelligence', source:'https://github.com/ken-kaneki21/job-portal', title:'Job Intelligence', category:'Retrieval & workflow reliability',
    lead:'A job-ranking pipeline evaluated against synthetic AI, data and backend search intents.',
    facts:[{label:'Holdout postings',value:'15'},{label:'Ranking methods',value:'4'},{label:'Chosen ranker',value:'Rules'}],
    sections:[
      {label:'Problem and contribution',text:'Candidates need recommendations that respect hard eligibility. I implemented mandatory experience handling, a worker recovery gate and an offline relevance comparison against lexical and MiniLM alternatives.'},
      {label:'Architecture and scope',text:'FastAPI serves persisted rankings. PostgreSQL/pgvector stores data and Temporal orchestrates workflows. Acceptance replay used a cached synthetic source, one login and a controlled worker restart between activities.'},
      {label:'Baseline and result',text:'The deterministic ranker reached 0.943 nDCG@5 across three holdout intents. Dense and hybrid reached 0.955. The gain fell below the adoption threshold and dense query time was higher, so the current ranker stayed.'},
      {label:'Limitations',text:'Retrieval ran offline on CPU with fully judged synthetic pools and authored labels. Human relevance review and live-source throughput remain unmeasured. The small scratch-model LoRA adapter was rejected after held-out evaluation.'}
    ],
    evidence:[{name:'Retrieval comparison and rankings',path:'evidence/retrieval-result.json'},{name:'Workflow acceptance',path:'evidence/job-acceptance.json'}]
  },
  {
    id:'evidenceworks', source:'https://github.com/ken-kaneki21/EvidenceWorks', title:'EvidenceWorks', category:'Evaluation & reproducibility',
    lead:'A local toolkit for comparing mapped AI answers and dashboard KPIs with an independent reference.',
    facts:[{label:'Host tests passed',value:'52'},{label:'Seeded oracle comparisons',value:'288'},{label:'Browser transport',value:'Local HTTP'}],
    sections:[
      {label:'Problem and contribution',text:'Two dashboards can agree on the wrong number. I built a Python and DuckDB toolkit with versioned metric definitions, input snapshots, evaluation reports and a separate visual validation harness.'},
      {label:'Architecture and scope',text:'DuckDB reads local synthetic inputs and an independent Fraction oracle provides comparison values. A Windows Python host ran the native checks. Playwright used Chromium over real loopback HTTP for the accepted browser run. The visual harness uses a synthetic test actor.'},
      {label:'Baseline and result',text:'DuckDB matched 24 hand-worked cases and 288 seeded comparisons. Both USD 99 observations failed against USD 100. The loopback browser passed, and the harness detected an intentionally clipped layout while the numeric KPI stayed correct.'},
      {label:'Limitations',text:'The suite covers authored fixtures. Metric sign-off, human baseline approval, UX calibration and independent installation remain pending. The original generic source is MIT-licensed; third-party notices remain separate.'}
    ],
    evidence:[{name:'EvidenceWorks report index',path:'evidence/evidenceworks/index.html'},{name:'Synthetic dashboard demo',path:'evidence/evidenceworks-demo.html'}]
  }
];

export const publicProfile = {name:'Saurabh',location:'Bengaluru, India',resume:'saurabh-public-resume.pdf', contact: null as null | { href:string; label:string }};
