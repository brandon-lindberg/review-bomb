import Image from "@/components/AppImage";

interface GameAvatarProps {
  title: string;
  imageUrl?: string | null;
  width: number;
  height: number;
  sizes?: string;
  className?: string;
}

export function GameAvatar({
  title,
  imageUrl,
  width,
  height,
  sizes,
  className = "",
}: GameAvatarProps) {
  if (imageUrl) {
    return (
      <Image
        src={imageUrl}
        alt={title}
        width={width}
        height={height}
        sizes={sizes ?? `${width}px`}
        className={`block ${className}`.trim()}
      />
    );
  }

  return (
    <div
      className={`flex items-center justify-center bg-gray-200 ${className}`.trim()}
      aria-hidden="true"
    >
      <span className="text-gray-500 font-medium">
        {title.charAt(0)}
      </span>
    </div>
  );
}
