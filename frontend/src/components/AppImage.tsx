import NextImage, { type ImageProps } from "next/image";
import { isRemoteImageUrl, normalizeImageUrl } from "@/lib/image-url";

export default function AppImage({
  src,
  unoptimized,
  ...props
}: ImageProps) {
  const normalizedSrc = typeof src === "string" ? normalizeImageUrl(src) : src;
  const shouldBypassOptimization =
    unoptimized ?? (typeof normalizedSrc === "string" && isRemoteImageUrl(normalizedSrc));

  return (
    <NextImage
      {...props}
      src={normalizedSrc}
      unoptimized={shouldBypassOptimization}
    />
  );
}
