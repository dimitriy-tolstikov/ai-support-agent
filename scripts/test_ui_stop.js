// Проверка кнопки «Стоп»: во время стриминга кнопка видна, после клика возвращается «Отправить»
// Запуск: NODE_PATH=../HhVacancyMonitor/node_modules node scripts/test_ui_stop.js
const { chromium } = require("playwright");

(async () => {
  const browser = await chromium.launch();
  const page = await browser.newPage();
  await page.goto("http://127.0.0.1:5173/", { waitUntil: "load" });
  await page.getByRole("button", { name: "Новый диалог" }).click();
  await page.waitForURL(/\/c\//);
  await page.getByPlaceholder(/Сообщение/).fill("расскажи что-нибудь");
  await page.getByRole("button", { name: "Отправить" }).click();
  await page.getByRole("button", { name: "Стоп" }).waitFor({ timeout: 10000 });
  console.log("stop button visible during streaming: OK");
  await page.getByRole("button", { name: "Стоп" }).click();
  await page.getByRole("button", { name: "Отправить" }).waitFor({ timeout: 5000 });
  console.log("composer back to 'Отправить' after stop: OK");
  await browser.close();
})().catch((e) => {
  console.error("FAIL:", e.message);
  process.exit(1);
});
