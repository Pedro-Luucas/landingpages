import { createElement, type ImgHTMLAttributes } from "react";

type MockImageProps = ImgHTMLAttributes<HTMLImageElement> & {
  src: string;
  alt: string;
  width?: number | `${number}`;
  height?: number | `${number}`;
  fill?: boolean;
  priority?: boolean;
  sizes?: string;
  unoptimized?: boolean;
};

export default function Image({
  src,
  alt,
  width,
  height,
  className,
  fill,
  priority,
  sizes,
  unoptimized,
  ...rest
}: MockImageProps) {
  void fill;
  void priority;
  void sizes;
  void unoptimized;
  return createElement("img", {
    src,
    alt,
    width,
    height,
    className,
    ...rest,
  });
}

export { Image };
