import Image from "next/image";

interface GameAvatarProps {
  title: string;
  imageUrl?: string | null;
  size: number;
  sizes: string;
  className?: string;
}

export function GameAvatar({
  title,
  imageUrl,
  size,
  sizes,
  className = "",
}: GameAvatarProps) {
  if (imageUrl) {
    return (
      <Image
        src={imageUrl}
        alt={title}
        width={size}
        height={size}
        sizes={sizes}
        className={className}
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
