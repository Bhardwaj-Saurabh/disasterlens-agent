// Localized strings for the seeker UI. Keys are Latin slugs; values are the
// surface text shown in each supported language. Languages are limited to
// those the agent actually handles end-to-end today (en/es/ar/vi/zh/fr). A
// native-Spanish-speaker review is on the Sprint-3 checklist; the other
// non-English strings are domain-grounded but should be reviewed before
// recording the demo.

export type Locale = "en" | "es" | "ar" | "vi" | "zh" | "fr";

export const LOCALES: { code: Locale; native: string; rtl?: boolean }[] = [
  { code: "en", native: "English" },
  { code: "es", native: "Español" },
  { code: "ar", native: "العربية", rtl: true },
  { code: "vi", native: "Tiếng Việt" },
  { code: "zh", native: "中文" },
  { code: "fr", native: "Français" },
];

interface Strings {
  app_title: string;
  app_subtitle: string;
  intro: string;
  language_label: string;
  message_placeholder: string;
  photo_label: string;
  photo_attached: string;
  photo_remove: string;
  send: string;
  searching: string;
  searching_subtext: string;
  empty_transcript: string;
  attached_inline: string;
  error_generic: string;
  privacy_note: string;
}

export const STRINGS: Record<Locale, Strings> = {
  en: {
    app_title: "DisasterLens",
    app_subtitle: "Help finding a loved one after the storm",
    intro: "Tell us about the person you're looking for. Write in your own language — we'll search shelter rosters, missing-person reports, and recent social posts. A human verifier will review every match before anything is sent.",
    language_label: "Language",
    message_placeholder: "Describe the person — name, age, what they were wearing, where you last saw them…",
    photo_label: "Attach a photo (optional)",
    photo_attached: "Photo attached",
    photo_remove: "Remove",
    send: "Search",
    searching: "Searching shelter rosters and recent reports…",
    searching_subtext: "This can take up to two minutes while the verifier reviews. Please don't refresh.",
    empty_transcript: "Your search results will appear here.",
    attached_inline: "(photo attached)",
    error_generic: "Something went wrong. Please try again.",
    privacy_note: "Information you share here is treated under the FEMA / NCMEC Post-Disaster Reunification of Children (2013) guidance. Minor disclosures require guardian verification.",
  },
  es: {
    app_title: "DisasterLens",
    app_subtitle: "Ayuda para encontrar a un ser querido después de la tormenta",
    intro: "Cuéntenos sobre la persona que está buscando. Escriba en su propio idioma — buscaremos en los registros de refugios, los reportes de personas desaparecidas y publicaciones recientes. Un verificador humano revisará cada coincidencia antes de enviar cualquier mensaje.",
    language_label: "Idioma",
    message_placeholder: "Describa a la persona — nombre, edad, qué llevaba puesto, dónde la vio por última vez…",
    photo_label: "Adjuntar una foto (opcional)",
    photo_attached: "Foto adjunta",
    photo_remove: "Quitar",
    send: "Buscar",
    searching: "Buscando en los registros de refugios y reportes recientes…",
    searching_subtext: "Esto puede tomar hasta dos minutos mientras el verificador revisa. Por favor no recargue la página.",
    empty_transcript: "Sus resultados aparecerán aquí.",
    attached_inline: "(foto adjunta)",
    error_generic: "Algo salió mal. Por favor intente de nuevo.",
    privacy_note: "La información que comparta aquí se trata bajo la guía FEMA / NCMEC de Reunificación de Niños tras Desastres (2013). La divulgación de menores requiere verificación del tutor.",
  },
  ar: {
    app_title: "DisasterLens",
    app_subtitle: "المساعدة في العثور على شخص عزيز بعد العاصفة",
    intro: "أخبرنا عن الشخص الذي تبحث عنه. اكتب بلغتك — سنبحث في سجلات الملاجئ وتقارير المفقودين والمنشورات الأخيرة. سيقوم محقق بشري بمراجعة كل نتيجة قبل إرسال أي رسالة.",
    language_label: "اللغة",
    message_placeholder: "صف الشخص — الاسم، العمر، ما كان يرتديه، آخر مكان رأيته فيه…",
    photo_label: "إرفاق صورة (اختياري)",
    photo_attached: "تم إرفاق الصورة",
    photo_remove: "إزالة",
    send: "بحث",
    searching: "نبحث في سجلات الملاجئ والتقارير الأخيرة…",
    searching_subtext: "قد يستغرق هذا حتى دقيقتين أثناء مراجعة المحقق. يرجى عدم تحديث الصفحة.",
    empty_transcript: "ستظهر نتائج البحث هنا.",
    attached_inline: "(صورة مرفقة)",
    error_generic: "حدث خطأ ما. يرجى المحاولة مرة أخرى.",
    privacy_note: "تعامل المعلومات التي تشاركها هنا وفقًا لإرشادات FEMA / NCMEC لإعادة لم شمل الأطفال بعد الكوارث (2013). يتطلب الإفصاح عن القاصرين التحقق من ولي الأمر.",
  },
  vi: {
    app_title: "DisasterLens",
    app_subtitle: "Hỗ trợ tìm kiếm người thân sau cơn bão",
    intro: "Hãy cho chúng tôi biết về người bạn đang tìm. Viết bằng ngôn ngữ của bạn — chúng tôi sẽ tìm trong danh sách trại tạm trú, báo cáo người mất tích, và các bài đăng gần đây. Một người xác minh sẽ kiểm tra từng kết quả trước khi gửi bất kỳ tin nhắn nào.",
    language_label: "Ngôn ngữ",
    message_placeholder: "Mô tả người đó — tên, tuổi, đang mặc gì, lần cuối bạn thấy họ ở đâu…",
    photo_label: "Đính kèm ảnh (tùy chọn)",
    photo_attached: "Đã đính kèm ảnh",
    photo_remove: "Xóa",
    send: "Tìm kiếm",
    searching: "Đang tìm trong danh sách trại tạm trú và báo cáo gần đây…",
    searching_subtext: "Quá trình này có thể mất tới hai phút trong khi người xác minh kiểm tra. Vui lòng không tải lại trang.",
    empty_transcript: "Kết quả tìm kiếm sẽ hiển thị ở đây.",
    attached_inline: "(có ảnh đính kèm)",
    error_generic: "Đã xảy ra lỗi. Vui lòng thử lại.",
    privacy_note: "Thông tin bạn chia sẻ ở đây được xử lý theo hướng dẫn của FEMA / NCMEC về Tái hợp Trẻ em sau Thảm họa (2013). Việc tiết lộ thông tin của trẻ vị thành niên yêu cầu xác minh người giám hộ.",
  },
  zh: {
    app_title: "DisasterLens",
    app_subtitle: "风暴过后帮助寻找亲人",
    intro: "请告诉我们您要找的人。用您自己的语言书写——我们将在避难所登记表、失踪人员报告和最近的社交帖子中搜索。每次匹配都将由人工核实员审核,然后才会发送任何消息。",
    language_label: "语言",
    message_placeholder: "描述这个人——姓名、年龄、当时穿着什么、您最后一次见到他/她的地点……",
    photo_label: "上传照片(可选)",
    photo_attached: "已附上照片",
    photo_remove: "移除",
    send: "搜索",
    searching: "正在搜索避难所登记表和最近的报告……",
    searching_subtext: "在核实员审核期间,这可能需要长达两分钟。请勿刷新页面。",
    empty_transcript: "搜索结果将显示在此处。",
    attached_inline: "(已附照片)",
    error_generic: "出现错误。请重试。",
    privacy_note: "您在此分享的信息将根据 FEMA / NCMEC《灾后儿童团聚指南(2013)》进行处理。涉及未成年人的信息披露需要监护人核实。",
  },
  fr: {
    app_title: "DisasterLens",
    app_subtitle: "Aide pour retrouver un proche après la tempête",
    intro: "Parlez-nous de la personne que vous cherchez. Écrivez dans votre langue — nous chercherons dans les registres des refuges, les rapports de personnes disparues et les publications récentes. Un vérificateur humain examinera chaque correspondance avant l'envoi de tout message.",
    language_label: "Langue",
    message_placeholder: "Décrivez la personne — nom, âge, ce qu'elle portait, où vous l'avez vue pour la dernière fois…",
    photo_label: "Joindre une photo (facultatif)",
    photo_attached: "Photo jointe",
    photo_remove: "Retirer",
    send: "Rechercher",
    searching: "Recherche dans les registres des refuges et les rapports récents…",
    searching_subtext: "Cela peut prendre jusqu'à deux minutes pendant la vérification. Veuillez ne pas actualiser la page.",
    empty_transcript: "Vos résultats de recherche apparaîtront ici.",
    attached_inline: "(photo jointe)",
    error_generic: "Une erreur s'est produite. Veuillez réessayer.",
    privacy_note: "Les informations que vous partagez ici sont traitées conformément aux directives FEMA / NCMEC de Réunification des Enfants après Catastrophe (2013). La divulgation concernant un mineur nécessite la vérification du tuteur.",
  },
};

// Heuristic locale detection from the first character of the seeker's text.
// Used to switch RTL direction even before the user has manually picked a
// locale. Conservative: only fires on unambiguous scripts.
export function detectLocale(text: string): Locale | null {
  if (!text) return null;
  const ch = text.trim().charCodeAt(0);
  if (ch >= 0x0600 && ch <= 0x06ff) return "ar";        // Arabic
  if (ch >= 0x4e00 && ch <= 0x9fff) return "zh";        // CJK Unified
  if (ch >= 0x1ea0 && ch <= 0x1ef9) return "vi";        // Vietnamese Latin Ext.
  return null;
}

export function isRtl(locale: Locale): boolean {
  return LOCALES.find((l) => l.code === locale)?.rtl === true;
}
