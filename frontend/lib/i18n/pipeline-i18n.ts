import type { Messages } from "./zh";
import { PIPELINE_NODES, type GraphNodeDef } from "@/lib/pipeline-graph";

type NodeId = keyof Messages["pipelineGraph"]["nodes"];

export function localizedPipelineNodes(messages: Messages): GraphNodeDef[] {
  const labels = messages.pipelineGraph.nodes;
  return PIPELINE_NODES.map((node) => {
    const loc = labels[node.id as NodeId];
    return loc ? { ...node, label: loc.label, short: loc.short } : node;
  });
}

export function localizedMainAgentPhase(activeStep: string | undefined, messages: Messages): string {
  const p = messages.pipelineGraph.phases;
  switch (activeStep) {
    case "planning":
      return p.planning;
    case "classifying":
      return p.classifying;
    case "vision_parsing":
      return p.vision_parsing;
    case "parsing":
    case "extracting":
      return p.parsing;
    case "running_rules":
      return p.running_rules;
    case "cross_checking":
      return p.cross_checking;
    case "adjudicating":
    case "generating_report":
      return p.adjudicating;
    default:
      return p.default;
  }
}
