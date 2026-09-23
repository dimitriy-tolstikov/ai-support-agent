// Скриншоты UI для README (запуск: NODE_PATH=../HhVacancyMonitor/node_modules node scripts/take_screenshots.js)
const path = require("path");
const { chromium } = require("playwright");

(async () => {
  const browser = await chromium.launch();
  const page = await browser.newPage({ viewport: { width: 1100, height: 750 } });

  // 1. Список диалогов
  await page.goto("http://127.0.0.1:5173/", { waitUntil: "load" });
  await page.waitForSelector("text=открыт", { timeout: 15000 });
  await page.waitForTimeout(500);
  await page.screenshot({ path: path.join(__dirname, "../docs/screenshots/list.png") });

  // 2. Новый диалог, вопрос про заказ, ждём tool_call и конец стриминга
  await page.getByRole("button", { name: "Новый диалог" }).click();
  await page.waitForURL(/\/c\//);
  await page.getByPlaceholder(/Сообщение/).fill("где мой заказ 1001?");
  await page.getByRole("button", { name: "Отправить" }).click();
  await page.waitForSelector("text=TTFT", { timeout: 20000 });
  await page.getByText(/вызовы инструментов/).click();
  await page.waitForTimeout(400);
  await page.screenshot({ path: path.join(__dirname, "../docs/screenshots/chat.png") });

  await browser.close();
  console.log("screenshots saved");
})().catch((e) => {
  console.error(e);
  process.exit(1);
});
