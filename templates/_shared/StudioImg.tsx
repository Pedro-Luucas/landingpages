import Image from "next/image";
import type { StudioImage } from "@/lib/view-model";

type StudioImgProps = {
  image: StudioImage;
  className?: string;
  priority?: boolean;
  sizes?: string;
};

export function StudioImg({
  image,
  className,
  priority,
  sizes,
}: StudioImgProps) {
  return (
    <Image
      src={image.src}
      alt={image.alt}
      width={image.width}
      height={image.height}
      className={className}
      priority={priority}
      sizes={sizes ?? "(max-width: 768px) 100vw, 960px"}
    />
  );
}
