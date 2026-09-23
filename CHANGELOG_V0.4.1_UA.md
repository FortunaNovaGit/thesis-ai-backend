# v0.4.1 — діагностика plugin/Elementor build

- Backend повертає конкретний список `failed_actions` замість лише загального лічильника.
- WordPress admin показує ability, plugin/page target і точну помилку.
- REST-клієнт зберігає WordPress error code/message для 401/403.
- Plugin installation preflight перевіряє `get_filesystem_method()` і в MVP автоматично встановлює plugins лише при `direct` filesystem access.
- Перед Plugin_Upgrader явно ініціалізується WP_Filesystem.
- Діагностика показує Plugin management та Filesystem method.
