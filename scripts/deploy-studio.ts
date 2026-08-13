import { JsonStateRepository } from "../lib/repositories/state-repository";
import { JsonStudioRepository } from "../lib/repositories/studio-repository";
import { deployStudio } from "../lib/vercel";

async function main() {
  const studioId = process.argv[2]?.trim();
  if (!studioId) throw new Error("Usage: npm run deploy:studio -- <studioId>");
  const studios = new JsonStudioRepository();
  const approved = await studios.getApproved(studioId);
  if (!approved) throw new Error(`No approved snapshot for ${studioId}`);
  const state = new JsonStateRepository(undefined, studios);
  const item = await state.getItem(studioId);
  if (item?.status !== "approved") throw new Error(`Deploy requires approved status; found ${item?.status ?? "missing"}`);
  const deployment = await deployStudio({ studioId, generationId: approved.generationId, approved, actor: "cli:human" });
  await studios.saveDeployment(deployment);
  await state.transition(studioId, "deploying", "cli:human", "Production deploy requested through Vercel hook.");
  process.stdout.write(`${JSON.stringify(deployment, null, 2)}\n`);
}

main().catch((error) => {
  process.stderr.write(`${error instanceof Error ? error.message : String(error)}\n`);
  process.exitCode = 1;
});
