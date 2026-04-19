interface Props {
  name: string;
  imgUrl: string;
  detail: string;
  variant: "sold" | "bought";
  team?: string;
}

export default function PlayerCard({ name, imgUrl, detail, variant, team }: Props) {
  const arrowColor = variant === "sold" ? "text-red-500" : "text-green-500";
  const arrow = variant === "sold" ? "↓" : "↑";

  return (
    <div className="flex items-center gap-2.5 py-1.5">
      {imgUrl ? (
        <img
          src={imgUrl}
          alt={name}
          className="w-10 h-10 rounded-full object-cover bg-gray-700 shrink-0"
          onError={(e) => {
            (e.target as HTMLImageElement).style.display = "none";
          }}
        />
      ) : (
        <div className="w-10 h-10 rounded-full bg-gray-300 shrink-0" />
      )}
      <div className="min-w-0 flex-1">
        <div className="font-semibold text-sm truncate">
          {name}
          {team && <span className="ml-1.5 text-xs text-gray-400 font-normal">{team}</span>}
          <span className={`ml-1.5 font-bold ${arrowColor}`}>{arrow}</span>
        </div>
        <div className="text-xs text-gray-400 truncate">{detail}</div>
      </div>
    </div>
  );
}
