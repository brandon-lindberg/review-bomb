import NextImage, { type ImageProps } from "next/image";
import { isRemoteImageUrl, normalizeImageUrl } from "@/lib/image-url";

export default function AppImage({
  src,
  unoptimized,
  quality,
  ...props
}: ImageProps) {
  const normalizedSrc = typeof src === "string" ? normalizeImageUrl(src) : src;
  const shouldBypassOptimization =
    typeof normalizedSrc === "string" && isRemoteImageUrl(normalizedSrc)
      ? true
      : Boolean(unoptimized);

  return (
    <NextImage
      {...props}
      src={normalizedSrc}
      {...(!shouldBypassOptimization && quality != null ? { quality } : {})}
      unoptimized={shouldBypassOptimization}
    />
  );
}
