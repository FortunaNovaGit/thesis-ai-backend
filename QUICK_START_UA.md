# QUICK START — v0.4 Elementor + Plugins

1. Онови backend repository файлами v0.4 і зроби Push. Render зробить auto-deploy.
2. Перевір: `https://YOUR-SERVICE.onrender.com/health` → version `0.4.1`.
3. У WordPress онови Thesis AI Bridge до v0.4.1.
4. AI Website Builder має лишитися підключеним. Якщо Render Free втратив connection state після redeploy — натисни Disconnect/Connect ще раз.
5. У формі Build вибери **Elementor Free — основний**.
6. Залиш увімкненим **Автоматично встановлювати/активувати потрібні approved plugins**.
7. Запусти build.

Система перед planning прочитає весь список встановлених plugins. Якщо Elementor:
- active → повторно не встановлюється;
- installed/inactive → активується;
- missing → встановлюється з WordPress.org та активується;
- install недоступний через filesystem policy хостингу → build поверне конкретну помилку, Elementor можна встановити вручну, після чого наступний build його автоматично побачить.

Після успіху AI draft-сторінки мають мати посилання **Elementor** у блоці останнього результату та відкриватися у Elementor editor.
