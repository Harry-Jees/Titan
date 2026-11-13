import {describe,expect,it} from "vitest";
import {complete} from "../src/model";

function fakeDb(allow=true):any{
 return {prepare:()=>({bind:()=>({first:async()=>allow?{reserved_neurons:120}:null})})};
}
describe("Titan GPT-OSS inference boundary",()=>{
 it("calls only the configured GPT-OSS-20B Workers AI model",async()=>{
  const calls:any[]=[];
  const env={DB:fakeDb(),AI:{run:async(model:string,input:any)=>{calls.push({model,input});return {choices:[{message:{content:"Reasoned response"}}]};}}} as any;
  const result=await complete(env,[{role:"user",content:"hello"}]);
  expect(result.text).toBe("Reasoned response");
  expect(result.model).toBe("@cf/openai/gpt-oss-20b");
  expect(calls).toHaveLength(1);
  expect(calls[0].model).toBe("@cf/openai/gpt-oss-20b");
  expect(calls[0].input.max_tokens).toBe(1200);
 });
 it("fails closed when the protected free-inference budget is exhausted",async()=>{
  let calls=0;
  const env={DB:fakeDb(false),AI:{run:async()=>{calls++;return {response:"should not run"};}}} as any;
  await expect(complete(env,[{role:"user",content:"hello"}])).rejects.toThrow("protected daily free-inference budget");
  expect(calls).toBe(0);
 });
 it("fails clearly when the Workers AI binding is missing",async()=>{
  await expect(complete({DB:fakeDb()} as any,[{role:"user",content:"hello"}])).rejects.toThrow("Titan AI binding is missing");
 });
});
