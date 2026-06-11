import i18n from "i18next";
import { initReactI18next } from "react-i18next";
import LanguageDetector from "i18next-browser-languagedetector";
import en from "./locales/en";
import ru from "./locales/ru";
import kk from "./locales/kk";

export const LANGUAGES = [
  { code: "ru", label: "РУ" },
  { code: "en", label: "EN" },
  { code: "kk", label: "ҚАЗ" },
] as const;

i18n
  .use(LanguageDetector)
  .use(initReactI18next)
  .init({
    resources: {
      en: { translation: en },
      ru: { translation: ru },
      kk: { translation: kk },
    },
    fallbackLng: "en",
    supportedLngs: ["en", "ru", "kk"],
    interpolation: { escapeValue: false }, // React already escapes
    detection: {
      order: ["localStorage", "navigator"],
      caches: ["localStorage"],
      lookupLocalStorage: "archvision_lang",
    },
  });

export default i18n;
