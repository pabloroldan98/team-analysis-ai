import type { Lang } from "../types";
import { t } from "../i18n";

interface Props {
  lang: Lang;
  onLangChange: (l: Lang) => void;
}

export default function Header({ lang, onLangChange }: Props) {
  return (
    <header className="bg-primary-dark text-white">
      <div className="max-w-6xl mx-auto px-4 py-4 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <img
            src="/assets/logo-dark.png"
            alt="SoccerSolver"
            className="h-10 object-contain"
          />
          <div>
            <h1 className="text-xl font-bold leading-tight">{t(lang, "title")}</h1>
            <p className="text-secondary text-xs">{t(lang, "subtitle")}</p>
          </div>
        </div>
        <div className="flex gap-2">
          <button
            onClick={() => onLangChange("es")}
            className={`px-3 py-1 rounded text-sm font-medium transition-colors ${
              lang === "es"
                ? "bg-secondary text-primary-dark"
                : "bg-white/10 hover:bg-white/20"
            }`}
          >
            {t("es", "spanish")}
          </button>
          <button
            onClick={() => onLangChange("en")}
            className={`px-3 py-1 rounded text-sm font-medium transition-colors ${
              lang === "en"
                ? "bg-secondary text-primary-dark"
                : "bg-white/10 hover:bg-white/20"
            }`}
          >
            {t("en", "english")}
          </button>
        </div>
      </div>
    </header>
  );
}
