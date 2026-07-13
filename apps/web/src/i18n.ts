import i18n from "i18next";
import { initReactI18next } from "react-i18next";
import LanguageDetector from "i18next-browser-languagedetector";

import en from "./locales/en.json";

import de from "./locales/de.json";

i18n
  .use(LanguageDetector)
  .use(initReactI18next)
  .init({
    resources: {
      en: { translation: en },
      de: { translation: de },
    },
    fallbackLng: "en",
    interpolation: {
      escapeValue: false,
    },
    detection: {
      order: ["localStorage", "navigator"],
      caches: ["localStorage"],
    },
  });

export default i18n;

export function tPlaceCategory(category: string | null | undefined): string {
  if (!category) return "";
  return i18n.t(`places.categories.${category}`, { defaultValue: category });
}

export function tPopupLabel(key: string): string {
  return i18n.t(`popup.${key}`);
}
