import {describe,expect,it} from "vitest";
import {encodeVector} from "../src/embeddings";
import {KNOWLEDGE_RETRIEVAL_LIMITS,knowledgeSearchTerms,retrieveKnowledge} from "../src/knowledge";

const queryVector=Array.from({length:1024},(_,index)=>index===0?1:0);
const encodedQueryVector=encodeVector(queryVector);

function createEnv(options:{
 lexical?:any[];
 vectors?:any[];
 conflicts?:any[];
}={}):{env:any;statements:{sql:string;params:unknown[]}[]}{
 const statements:{sql:string;params:unknown[]}[]=[];
 const DB={
  prepare(sql:string){
   const query:any={
    params:[] as unknown[],
    bind(...values:unknown[]){query.params=values;return query;},
    async first(){return {reserved_neurons:1};},
    async all(){
     statements.push({sql,params:query.params});
     if(sql.includes("knowledge_units_fts MATCH"))return {results:options.lexical||[]};
     if(sql.includes("embedding_json IS NOT NULL"))return {results:options.vectors||[]};
     if(sql.includes("knowledge_facts f"))return {results:options.conflicts||[]};
     return {results:[]};
    }
   };
   return query;
  }
 };
 const AI={run:async()=>({data:[queryVector]})};
 return {env:{DB,AI},statements};
}

describe("bounded hybrid knowledge retrieval",()=>{
 it("normalizes and caps lexical terms before building an FTS query",()=>{
  const terms=knowledgeSearchTerms("the alpha alpha and bravo charlie delta echo foxtrot golf hotel india juliet kilo lima");
  expect(terms).toEqual(["alpha","bravo","charlie","delta","echo","foxtrot","golf","hotel","india","juliet"]);
  expect(terms).toHaveLength(KNOWLEDGE_RETRIEVAL_LIMITS.maxQueryTerms);
 });

 it("keeps regular and conflicting evidence inside one total context budget",async()=>{
  const vectors=[
   {id:"semantic-1",source_url:"https://example.org/a",title:"A",content:"Short semantic evidence A.",summary:"",kind:"fact",embedding_json:encodedQueryVector},
   {id:"semantic-2",source_url:"https://example.org/b",title:"B",content:"Short semantic evidence B.",summary:"",kind:"concept",embedding_json:encodedQueryVector}
  ];
  const conflicts=Array.from({length:8},(_,index)=>({
   subject:"Titan subject "+index,
   predicate:"has a disputed property",
   object:"alternative evidence ".repeat(20),
   explanation:"This explanation records why the claim remains unresolved. ".repeat(8),
   source_url:"https://conflicts.example/source-"+index,
   quote:"The source provides a competing observation. ".repeat(10)
  }));
  const {env,statements}=createEnv({vectors,conflicts});
  const result=await retrieveKnowledge(
   env,
   "alpha bravo charlie delta echo foxtrot golf hotel india juliet kilo lima"
  );

  expect(result.context.length).toBeLessThanOrEqual(KNOWLEDGE_RETRIEVAL_LIMITS.contextCharacters);
  expect(result.context).toContain("[Titan has not resolved these conflicting claims.");
  expect(result.context).toContain("Unresolved conflicting evidence:");
  expect(result.sources.some(source=>source.kind==="conflict")).toBe(true);

  const fts=statements.find(statement=>statement.sql.includes("knowledge_units_fts MATCH"));
  const vector=statements.find(statement=>statement.sql.includes("embedding_json IS NOT NULL"));
  const conflict=statements.find(statement=>statement.sql.includes("knowledge_facts f"));
  expect(fts?.sql).toContain("LIMIT "+KNOWLEDGE_RETRIEVAL_LIMITS.lexicalCandidates);
  expect((fts?.params[0] as string).split(" OR ")).toHaveLength(KNOWLEDGE_RETRIEVAL_LIMITS.maxQueryTerms);
  expect(vector?.sql).toContain("LIMIT "+KNOWLEDGE_RETRIEVAL_LIMITS.vectorCandidates);
  expect(conflict?.sql).toContain("LIMIT "+KNOWLEDGE_RETRIEVAL_LIMITS.conflictCandidates);
 });
});
