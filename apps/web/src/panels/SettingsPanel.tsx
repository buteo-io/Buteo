import { useTranslation } from "react-i18next";
import { useTheme, Theme } from "../hooks/useTheme";
import { Select } from "../components/Select";

type Props = {
  email?: string | null;
};

export function SettingsPanel({ email }: Props) {
  const { theme, setTheme } = useTheme();
  const { t, i18n } = useTranslation();

  const changeLanguage = (lng: string) => {
    i18n.changeLanguage(lng);
  };

  return (
    <div className="settings">
      <details className="settings-section" open>
        <summary>
          <span className="caret" aria-hidden="true">
            ▸
          </span>
          <span>{t("settings.appearance")}</span>
        </summary>
        <div className="settings-row" style={{ marginTop: "8px" }}>
          <span className="muted">{t("settings.theme")}</span>
          <Select
            value={theme}
            onChange={(val) => setTheme(val as Theme)}
            options={[
              { value: "system", label: t("settings.themeSystem") },
              { value: "light", label: t("settings.themeLight") },
              { value: "dark", label: t("settings.themeDark") },
            ]}
            style={{ minWidth: "120px" }}
          />
        </div>
        <div className="settings-row" style={{ marginTop: "8px" }}>
          <span className="muted">{t("settings.language")}</span>
          <Select
            value={i18n.language}
            onChange={(val) => changeLanguage(val)}
            options={[
              { value: "en", label: "English" },
              { value: "de", label: "Deutsch" },
            ]}
            style={{ minWidth: "120px" }}
          />
        </div>
      </details>

      <details className="settings-section">
        <summary>
          <span className="caret" aria-hidden="true">
            ▸
          </span>
          <span>{t("settings.account")}</span>
          <span className="muted small">coming soon</span>
        </summary>
        <p className="muted small">
          Changing email and password will come soon.
        </p>
        <div className="settings-row">
          <span className="muted">{t("settings.email")}</span>
          <span className="mono">{email ?? "—"}</span>
        </div>
        <div className="settings-row">
          <button className="ghost" disabled title="Coming soon">
            {t("settings.changeEmail")}…
          </button>
          <button className="ghost" disabled title="Coming soon">
            {t("settings.changePassword")}…
          </button>
        </div>
      </details>
    </div>
  );
}
