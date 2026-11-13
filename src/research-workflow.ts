import { WorkflowEntrypoint } from "cloudflare:workers";
import type { WorkflowEvent, WorkflowStep } from "cloudflare:workers";
import type { Env } from "./types";
import { RESEARCH_SEEDS, fetchResearchPage } from "./research";
import { learnFromPage } from "./knowledge";
type ResearchParams={runId:string;scheduledAt:number;durationSeconds?:number};

export class TitanResearchWorkflow extends WorkflowEntrypoint<Env,ResearchParams>{
 async run(event:WorkflowEvent<ResearchParams>,step:WorkflowStep):Promise<Record<string,unknown>>{
  const runId=event.payload.runId,scheduledAt=event.payload.scheduledAt||Date.now();
  const durationSeconds=Math.max(60,Math.min(1800,event.payload.durationSeconds||1800)),startedAt=scheduledAt,maxPages=240;
  await step.do("initialize-research-run",async()=>{
   await this.env.DB.prepare("INSERT OR IGNORE INTO research_runs(run_id,status,scheduled_at,started_at) VALUES(?,'running',?,CURRENT_TIMESTAMP)")
    .bind(runId,new Date(scheduledAt).toISOString()).run();
   await this.env.DB.batch(RESEARCH_SEEDS.map((url,index)=>this.env.DB.prepare("INSERT OR IGNORE INTO research_frontier(url,depth,priority,discovered_from,status) VALUES(?,0,?,'scheduled-seed','queued')").bind(url,100-index)));
   return {seeded:RESEARCH_SEEDS.length};
  });
  let processed=0,pagesCrawled=0,factsAdded=0,chunksAdded=0;
  while(processed<maxPages&&Date.now()-startedAt<durationSeconds*1000){
   const next=await step.do("claim-frontier-"+processed,async()=>{
    const row=await this.env.DB.prepare("SELECT url,depth FROM research_frontier WHERE status='queued' AND depth<=2 ORDER BY priority DESC,created_at ASC LIMIT 1").first<{url:string;depth:number}>();
    if(!row)return null;
    await this.env.DB.prepare("UPDATE research_frontier SET status='processing',attempts=attempts+1,updated_at=CURRENT_TIMESTAMP WHERE url=?").bind(row.url).run();
    return row;
   });
   if(!next)break;
   const page=await step.do("fetch-public-page-"+processed,async()=>fetchResearchPage(this.env,next.url));
   if(!page){
    await step.do("mark-unavailable-"+processed,async()=>{
     await this.env.DB.prepare("UPDATE research_frontier SET status='skipped',updated_at=CURRENT_TIMESTAMP WHERE url=?").bind(next.url).run();return true;
    });
   }else{
    const learned=await step.do("understand-and-index-"+processed,async()=>learnFromPage(this.env,page,runId));
    await step.do("queue-discovered-links-"+processed,async()=>{
     await this.env.DB.prepare("UPDATE research_frontier SET status='learned',updated_at=CURRENT_TIMESTAMP WHERE url=?").bind(next.url).run();
     const links=page.links.filter(link=>link!==page.url).slice(0,8);
     if(next.depth<2&&links.length)await this.env.DB.batch(links.map((link,index)=>this.env.DB.prepare("INSERT OR IGNORE INTO research_frontier(url,depth,priority,discovered_from,status) VALUES(?,?,?,?,'queued')").bind(link,next.depth+1,50-index,page.url)));
     await this.env.DB.prepare("UPDATE research_runs SET pages_crawled=pages_crawled+1,facts_added=facts_added+?,chunks_added=chunks_added+? WHERE run_id=?").bind(learned.factsAdded,learned.chunksAdded,runId).run();
     return links.length;
    });
    pagesCrawled++;factsAdded+=learned.factsAdded;chunksAdded+=learned.chunksAdded;
   }
   processed++;
   await step.sleep("crawl-pacing-"+processed,"1 second");
  }
  const remaining=await this.env.DB.prepare("SELECT COUNT(*) AS count FROM research_frontier WHERE status='queued'").first<{count:number}>();
  const status=remaining?.count?"partial":"completed";
  await step.do("finish-research-run",async()=>{
   await this.env.DB.prepare("UPDATE research_runs SET status=?,completed_at=CURRENT_TIMESTAMP WHERE run_id=?").bind(status,runId).run();return true;
  });
  return {runId,status,pagesCrawled,factsAdded,chunksAdded,queued:remaining?.count||0,processed};
 }
}
