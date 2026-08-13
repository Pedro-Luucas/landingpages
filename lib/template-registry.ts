import type { ComponentType } from "react";
import { BoldTemplate } from "@/templates/bold";
import { EditorialTemplate } from "@/templates/editorial";
import { ImmersiveTemplate } from "@/templates/immersive";
import { MinimalTemplate } from "@/templates/minimal";
import type { LandingTemplateProps } from "@/lib/view-model";

export const TEMPLATE_IDS = [
  "editorial",
  "immersive",
  "minimal",
  "bold",
] as const;

export type RegisteredTemplateId = (typeof TEMPLATE_IDS)[number];

const TEMPLATES: Record<
  RegisteredTemplateId,
  ComponentType<LandingTemplateProps>
> = {
  editorial: EditorialTemplate,
  immersive: ImmersiveTemplate,
  minimal: MinimalTemplate,
  bold: BoldTemplate,
};

export function listTemplates(): readonly RegisteredTemplateId[] {
  return TEMPLATE_IDS;
}

export function getTemplate(
  id: string,
): ComponentType<LandingTemplateProps> {
  if (id in TEMPLATES) {
    return TEMPLATES[id as RegisteredTemplateId];
  }
  return EditorialTemplate;
}
