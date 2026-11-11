<?php
/** Offline smoke for optional brief normalization; WordPress runtime E2E is separate. */
declare(strict_types=1);
define('ABSPATH', __DIR__ . '/');
function wp_unslash(string $value): string { return stripslashes($value); }
function sanitize_text_field(string $value): string { return trim(strip_tags($value)); }
function sanitize_key(string $value): string { return preg_replace('/[^a-z0-9_-]/', '', strtolower($value)); }
function absint($value): int { return abs((int)$value); }
function wp_attachment_is_image(int $id): bool { return in_array($id, [123, 124], true); }
require_once dirname(__DIR__) . '/includes/class-thesis-ai-bridge-admin.php';
$cls = new ReflectionClass('Thesis_AI_Bridge_Admin');
$collect = $cls->getMethod('collect_optional_brief');
$enrich = $cls->getMethod('enrich_prompt');
$brief = $collect->invoke(null, [
    'brief_brand' => '<b>Fortuna Nova</b>',
    'brief_product_count' => '24',
    'brief_colors' => '#382219, #EACD9B',
    'brief_assets' => 'none',
    'brief_facts' => 'Назви товарів перевірені.',
    'brief_hero_image_id' => '123',
    'brief_hero_secondary_image_id' => '124',
    'brief_products' => "Асорті 16 цукерок\nАсорті 24 цукерки\nАсорті 16 цукерок",
]);
assert($brief['brand'] === 'Fortuna Nova');
assert($brief['product_count'] === '24');
assert($brief['colors'] === '#382219, #EACD9B');
assert($brief['assets'] === 'none');
assert($brief['hero_image_id'] === '123');
assert($brief['hero_secondary_image_id'] === '124');
assert($brief['products'] === "Асорті 16 цукерок\nАсорті 24 цукерки");
$prompt = $enrich->invoke(null, 'Створи сайт Fortuna Nova у стилі editorial.', $brief);
assert(str_contains($prompt, 'Очікувана кількість товарів у каталозі: 24'));
assert(str_contains($prompt, 'не дозвіл вигадати товари'));
assert(str_contains($prompt, 'ПІДТВЕРДЖЕНІ назви демотоварів'));
assert(str_contains($prompt, '«Асорті 16 цукерок»; «Асорті 24 цукерки»'));
$invalid = $collect->invoke(null, [
    'brief_colors' => '#FFF; background:url(javascript:evil)',
    'brief_product_count' => '10; DROP TABLE',
    'brief_assets' => 'remote',
    'brief_hero_image_id' => '999',
    'brief_hero_secondary_image_id' => '123',
]);
assert($invalid['colors'] === '' && $invalid['product_count'] === '' && $invalid['assets'] === 'unsure');
assert($invalid['hero_image_id'] === '');
assert($invalid['hero_secondary_image_id'] === '123');
echo "PASS: sanitized optional brief, preserved truthful constraints, rejected invalid fields\n";

$dupe = $collect->invoke(null,['brief_hero_image_id'=>'123','brief_hero_secondary_image_id'=>'123']);
assert($dupe['hero_secondary_image_id'] === '');
