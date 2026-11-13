import { WorkflowEntrypoint } from "cloudflare:workers";
import type { WorkflowEvent, WorkflowStep } from "cloudflare:workers";
import type { Env } from "./types";
import { RESEARCH_SEEDS, fetchResearchPage } from "./research";
import { learnFromPage } from "./knowledge";
type ResearchParams={runId:string;scheduledAt:number;durationSeconds?:number};

export class TitanResearchWorkflow extends WorkflowEntrypoint<Env,ResearchParams>{
 async run(event:WorkflowEvent<ResearchParams>,step:WorkflowStep):Promise<Record<string,unknown>>{
  const runId=event.payload.runId,scheduledAt=Number.isFinite(event.payload.scheduledAt)?event.payload.scheduledAt:0;
  const durationSeconds=Math.max(60,Math.min(1800,event.payload.durationSeconds||1800));
  const startedAt=scheduledAt,maxPages=180;
  await step.do("initialize-research-run",async()=>{
   await this.env.DB.prepare("INSERT OR IGNORE INTO research_runs(run_id,status,scheduled_at,started_at) VALUES(?,'running',?,CURRENT_TIMESTAMP)").bind(runId,new Date(scheduledAt).toISOString()).run();
   await this.env.DB.prepare("UPDATE research_frontier SET status='queued',updated_at=CURRENT_TIMESTAMP WHERE status IN ('learned','unchanged','skipped') AND updated_at<datetime('now','-7 days')").run();
   await this.env.DB.prepare("UPDATE research_frontier SET status='queued',updated_at=CURRENT_TIMESTAMP WHERE status='failed' AND updated_at<datetime('now','-12 hours')").run();
   await this.env.DB.prepare("UPDATE research_frontier SET status='queued',updated_at=CURRENT_TIMESTAMP WHERE status='processing' AND updated_at<datetime('now','-1 hour')").run();
   await this.env.DB.batch(RESEARCH_SEEDS.map((url,index)=>this.env.DB.prepare("INSERT OR IGNORE INTO research_frontier(url,depth,priority,discovered_from,status) VALUES(?,0,?,'scheduled-seed','queued')").bind(url,100-index)));
   return {seeded:RESEARCH_SEEDS.length};
  });
  let processed=0,pagesCrawled=0,factsAdded=0,chunksAdded=0,stopReason="",failedPages=0;
  while(processed<maxPages){
   // Workflow replay must not branch on Date.now() outside a durable step.
   const checkedAt=await step.do("check-research-deadline-"+processed,async()=>Date.now());
   if(checkedAt-startedAt>=durationSeconds*1000){stopReason="time-limit";break;}
   const next=await step.do("claim-frontier-"+processed,async()=>{
    const row=await this.env.DB.prepare("SELECT url,depth FROM research_frontier WHERE status='queued' AND depth<=2 ORDER BY priority DESC,created_at ASC LIMIT 1").first<{url:string;depth:number}>();
    if(!row)return null;
    await this.env.DB.prepare("UPDATE research_frontier SET status='processing',attempts=attempts+1,updated_at=CURRENT_TIMESTAMP WHERE url=?").bind(row.url).run();
    return row;
   });
   if(!next)break;

   // Raw HTML/text stays inside this step's memory; only distilled knowledge and small metadata persist.
   const outcome=await step.do("fetch-understand-and-store-"+processed,async()=>{
    try{
     const page=await fetchResearchPage(this.env,next.url);
     if(!page){
      await this.env.DB.prepare("UPDATE research_frontier SET status='skipped',updated_at=CURRENT_TIMESTAMP WHERE url=?").bind(next.url).run();
      return {status:"skipped",factsAdded:0,chunksAdded:0,stopReason:""};
     }
     const previous=await this.env.DB.prepare("SELECT content_hash FROM research_pages WHERE source_url=?").bind(page.url).first<{content_hash:string}>();
     const unchanged=previous?.content_hash===page.contentHash;
     let learned={factsAdded:0,chunksAdded:0,summary:"unchanged page"};
     if(unchanged){
      await this.env.DB.prepare("UPDATE research_pages SET fetched_at=CURRENT_TIMESTAMP WHERE source_url=?").bind(page.url).run();
     }else{
      learned=await learnFromPage(this.env,page,runId);
     }
     await this.env.DB.prepare("UPDATE research_frontier SET status=?,updated_at=CURRENT_TIMESTAMP WHERE url=?").bind(unchanged?"unchanged":"learned",next.url).run();
     const links=page.links.filter(link=>link!==page.url).slice(0,8);
     if(next.depth<2&&links.length)await this.env.DB.batch(links.map((link,index)=>this.env.DB.prepare("INSERT OR IGNORE INTO research_frontier(url,depth,priority,discovered_from,status) VALUES(?,?,?,?,'queued')").bind(link,next.depth+1,50-index,page.url)));
     await this.env.DB.prepare("UPDATE research_runs SET pages_crawled=pages_crawled+1,facts_added=facts_added+?,chunks_added=chunks_added+? WHERE run_id=?").bind(learned.factsAdded,learned.chunksAdded,runId).run();
     return {status:unchanged?"unchanged":"learned",factsAdded:learned.factsAdded,chunksAdded:learned.chunksAdded,stopReason:""};
    }catch(error){
     const message=error instanceof Error?error.message:"Research page processing failed";
     await this.env.DB.prepare("UPDATE research_frontier SET status='failed',updated_at=CURRENT_TIMESTAMP WHERE url=?").bind(next.url).run();
     await this.env.DB.prepare("UPDATE research_runs SET status='partial',error=? WHERE run_id=?").bind(message.slice(0,1000),runId).run();
     return {status:/budget|capacity|binding/i.test(message)?"budget-exhausted":"failed",factsAdded:0,chunksAdded:0,stopReason:message};
    }
   });
   if(outcome.status==="learned"||outcome.status==="unchanged"){
    pagesCrawled++;factsAdded+=outcome.factsAdded;chunksAdded+=outcome.chunksAdded;
   }else if(outcome.status==="failed")failedPages++;
   if(outcome.status==="budget-exhausted"){stopReason=outcome.stopReason;break;}
   processed++;
   await step.sleep("crawl-pacing-"+processed,"1 second");
  }
  const remaining=await this.env.DB.prepare("SELECT COUNT(*) AS count FROM research_frontier WHERE status='queued'").first<{count:number}>();
  const status=(stopReason||remaining?.count||failedPages)?"partial":"completed";
  await step.do("finish-research-run",async()=>{
   await this.env.DB.prepare("UPDATE research_runs SET status=?,error=COALESCE(error,?),completed_at=CURRENT_TIMESTAMP WHERE run_id=?").bind(status,stopReason||null,runId).run();return true;
  });
  return {runId,status,pagesCrawled,factsAdded,chunksAdded,queued:remaining?.count||0,processed,failedPages,stopReason};
 }
}
