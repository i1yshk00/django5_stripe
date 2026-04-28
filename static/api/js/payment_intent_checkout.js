/**
 * Клиентский сценарий оплаты заказа через Stripe Payment Element и PaymentIntent.
 *
 * Последовательность работы:
 * 1. При загрузке страницы браузер запрашивает у Django `client_secret`.
 * 2. Stripe.js инициализирует `Payment Element` внутри нашей страницы.
 * 3. Пользователь подтверждает оплату через `stripe.confirmPayment(...)`.
 * 4. При синхронном успешном платеже браузер сразу переходит на success page.
 * 5. Финальный статус оплаты подтверждается webhook-слоем на сервере.
 */
document.addEventListener('DOMContentLoaded', async () => {
    const form = document.querySelector('[data-payment-intent-form]');
    const paymentElementNode = document.querySelector('[data-payment-element]');
    const errorNode = document.querySelector('[data-payment-error]');
    const submitButton = document.querySelector('[data-payment-submit]');

    if (!form || !paymentElementNode || !submitButton) {
        return;
    }

    /**
     * Показывает человекочитаемую ошибку рядом с формой оплаты.
     *
     * @param {string} message - Сообщение, которое увидит пользователь.
     */
    const showError = (message) => {
        if (errorNode) {
            errorNode.textContent = message;
        }
    };

    /**
     * Обновляет текст и состояние submit-кнопки.
     *
     * @param {boolean} isLoading - Идет ли активный запрос или подтверждение оплаты.
     * @param {string} label - Подпись кнопки в текущем состоянии.
     */
    const setLoading = (isLoading, label) => {
        submitButton.disabled = isLoading;
        submitButton.textContent = label;
    };

    const createPaymentIntentUrl = form.dataset.createPaymentIntentUrl;
    const publishableKey = form.dataset.publishableKey;

    if (!createPaymentIntentUrl) {
        showError('Не найден endpoint создания PaymentIntent.');
        return;
    }

    if (!publishableKey) {
        showError('На странице отсутствует publishable key Stripe.');
        return;
    }

    if (typeof window.Stripe !== 'function') {
        showError('Stripe.js не загрузился. Проверь подключение к сети.');
        return;
    }

    setLoading(true, 'Подготавливаем форму оплаты...');

    let stripe;
    let elements;
    let clientSecret = '';
    let returnUrl = '';

    try {
        stripe = window.Stripe(publishableKey);

        const response = await fetch(createPaymentIntentUrl, {
            method: 'GET',
            headers: {
                'Accept': 'application/json',
            },
        });

        const payload = await response.json().catch(() => ({}));

        if (!response.ok) {
            throw new Error(
                payload.error || 'Сервер не смог создать Stripe PaymentIntent.',
            );
        }

        if (!payload.client_secret) {
            throw new Error('Сервер не вернул client_secret PaymentIntent.');
        }

        if (!payload.return_url) {
            throw new Error('Сервер не вернул return_url для PaymentIntent.');
        }

        clientSecret = payload.client_secret;
        returnUrl = payload.return_url;

        const appearance = {
            theme: 'night',
            labels: 'floating',
        };

        elements = stripe.elements({
            clientSecret,
            appearance,
        });

        const paymentElement = elements.create('payment', {
            layout: 'accordion',
        });
        paymentElement.mount(paymentElementNode);

        paymentElementNode.classList.remove('loading');
        paymentElementNode.textContent = '';
        setLoading(false, 'Оплатить через Payment Intent');
    } catch (error) {
        paymentElementNode.classList.remove('loading');
        paymentElementNode.textContent = 'Не удалось инициализировать форму оплаты.';

        showError(
            error instanceof Error
                ? error.message
                : 'Не удалось подготовить Stripe Payment Element.',
        );
        setLoading(true, 'Оплата недоступна');
        return;
    }

    form.addEventListener('submit', async (event) => {
        event.preventDefault();

        if (!stripe || !elements || !clientSecret || !returnUrl) {
            showError('Форма оплаты не была корректно инициализирована.');
            return;
        }

        try {
            showError('');
            setLoading(true, 'Подтверждаем Payment Intent...');

            const {error, paymentIntent} = await stripe.confirmPayment({
                elements,
                clientSecret,
                confirmParams: {
                    return_url: returnUrl,
                },
                redirect: 'if_required',
            });

            if (error) {
                throw new Error(error.message);
            }

            if (paymentIntent) {
                const successUrl = new URL(returnUrl);
                successUrl.searchParams.set('payment_intent_id', paymentIntent.id);
                successUrl.searchParams.set('payment_intent_status', paymentIntent.status);
                window.location.href = successUrl.toString();
            }
        } catch (error) {
            showError(
                error instanceof Error
                    ? error.message
                    : 'Не удалось подтвердить Payment Intent.',
            );
            setLoading(false, 'Оплатить через Payment Intent');
        }
    });
});
