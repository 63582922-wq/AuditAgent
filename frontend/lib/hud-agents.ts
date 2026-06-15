/** 从 state_json 提取图谱用的专员 Agent（不含主 Agent / 视觉 / 文本 Ingest 固定节点） */

export type HudAgent = { id: string; name: string; station: string; modality?: string };

/** 已在图谱固定节点中展示的 Worker，不再重复渲染为子节点 */
export const PIPELINE_FIXED_AGENT_IDS = new Set(["main", "text_ingest", "vision_agent"]);

export function pickHudAgents(
  stateJson?: Record<string, unknown> | null
): HudAgent[] {
  if (!stateJson) return [];

  const mission = stateJson.mission as
    | { registered_agents?: HudAgent[]; tasks?: { assignee: string; assignee_name?: string }[] }
    | undefined;

  let agents: HudAgent[] = [];

  if (mission?.registered_agents?.length) {
    agents = mission.registered_agents
      .filter((a) => !PIPELINE_FIXED_AGENT_IDS.has(a.id))
      .map((a) => ({
        id: a.id,
        name: a.name,
        station: a.station || "",
        modality: a.modality,
      }));
  } else {
    const fromPlan =
      (stateJson.agent_plan as { sub_agents?: HudAgent[] } | undefined)?.sub_agents ||
      (stateJson.execution_graph as { sub_agents?: HudAgent[] } | undefined)?.sub_agents;

    if (fromPlan?.length) {
      agents = fromPlan
        .filter((a) => !PIPELINE_FIXED_AGENT_IDS.has(a.id))
        .map((a) => ({
          id: a.id,
          name: a.name,
          station: a.station || "",
        }));
    }
  }

  return agents;
}
