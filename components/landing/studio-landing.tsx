import type { StudioViewModel } from "@/lib/view-model";
import { BoldTemplate } from "@/templates/bold";
import { EditorialTemplate } from "@/templates/editorial";
import { ImmersiveTemplate } from "@/templates/immersive";
import { MinimalTemplate } from "@/templates/minimal";

export function StudioLanding({ studio }: { studio: StudioViewModel }) {
  switch (studio.templateId) {
    case "immersive":
      return <ImmersiveTemplate studio={studio} />;
    case "minimal":
      return <MinimalTemplate studio={studio} />;
    case "bold":
      return <BoldTemplate studio={studio} />;
    case "editorial":
    default:
      return <EditorialTemplate studio={studio} />;
  }
}
