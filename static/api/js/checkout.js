/**
 * Клиентский сценарий запуска Stripe Checkout с item detail страницы.
 *
 * Последовательность работы:
 * 1. Пользователь нажимает кнопку "Купить через Stripe".
 * 2. Браузер запрашивает у Django `/buy/<id>`.
 * 3. Django создает Checkout Session и возвращает `session.id`.
 * 4. Stripe.js выполняет redirect пользователя на hosted Checkout страницу.
 */
document.addEventListener('DOMContentLoaded', () => {
    const checkoutButton = document.querySelector('[data-checkout-button]');
    const errorNode = document.querySelector('[data-checkout-error]');

    if (!checkoutButton) {
        return;
    }

    /**
     * Показывает человекочитаемую ошибку рядом с кнопкой оплаты.
     *
     * @param {string} message - Текст ошибки, который увидит пользователь.
     */
    const showError = (message) => {
        if (errorNode) {
            errorNode.textContent = message;
        }
    };

    /**
     * Переключает визуальное состояние загрузки кнопки.
     *
     * @param {boolean} isLoading - Флаг активного запроса к серверу.
     */
    const setLoading = (isLoading) => {
        checkoutButton.disabled = isLoading;
        checkoutButton.textContent = isLoading
            ? 'Создаем Checkout Session...'
            : 'Купить через Stripe';
    };

    checkoutButton.addEventListener('click', async () => {
        const buyUrl = checkoutButton.dataset.buyUrl;
        const publishableKey = checkoutButton.dataset.publishableKey;

        if (!buyUrl) {
            showError('Не найден endpoint запуска оплаты.');
            return;
        }

        if (!publishableKey) {
            showError('На странице отсутствует публичный ключ Stripe.');
            return;
        }

        if (typeof window.Stripe !== 'function') {
            showError('Stripe.js не загрузился. Проверь подключение к сети.');
            return;
        }

        const stripe = window.Stripe(publishableKey);

        try {
            showError('');
            setLoading(true);

            const response = await fetch(buyUrl, {
                method: 'GET',
                headers: {
                    'Accept': 'application/json',
                },
            });

            const payload = await response.json().catch(() => ({}));

            if (!response.ok) {
                throw new Error(
                    payload.error || 'Сервер не смог создать платежную сессию.',
                );
            }

            if (!payload.id) {
                throw new Error('Сервер не вернул идентификатор Checkout Session.');
            }

            const result = await stripe.redirectToCheckout({
                sessionId: payload.id,
            });

            if (result.error) {
                throw new Error(result.error.message);
            }
        } catch (error) {
            showError(
                error instanceof Error
                    ? error.message
                    : 'Не удалось запустить Stripe Checkout.',
            );
        } finally {
            setLoading(false);
        }
    });
});
