// Функціональність для промокоду
document.addEventListener('DOMContentLoaded', function() {
    const promocodeBtn = document.querySelector('.basket__promocode-add-btn');
    const promocodeInput = document.querySelector('.basket__promocode input[type="text"]');
    
    if (promocodeBtn && promocodeInput) {
        promocodeBtn.addEventListener('click', function() {
            const promocode = promocodeInput.value.trim();
            
            if (!promocode) {
                alert('Введіть промокод');
                return;
            }
            
            // Показуємо індикатор завантаження
            promocodeBtn.textContent = 'Перевіряємо...';
            promocodeBtn.disabled = true;
            
            // Відправляємо запит на перевірку промокоду
            fetch('/api/check-promocode/', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': getCookie('csrftoken')
                },
                body: JSON.stringify({ promocode: promocode })
            })
            .then(response => response.json())
            .then(data => {
                if (data.success) {
                    // Оновлюємо ціни на сторінці
                    updatePricesWithDiscount(data);
                    
                    // Показуємо повідомлення про успіх
                    alert(data.message);
                    
                    // Зберігаємо промокод в localStorage
                    localStorage.setItem('applied_promocode', promocode);
                    
                    // Змінюємо вигляд кнопки
                    promocodeBtn.textContent = 'Застосовано';
                    promocodeBtn.classList.add('applied');
                } else {
                    throw new Error(data.error || 'Помилка при перевірці промокоду');
                }
            })
            .catch(error => {
                // Показуємо повідомлення про помилку
                alert(error.message);
                
                // Повертаємо кнопку в початковий стан
                promocodeBtn.textContent = 'Додати';
                promocodeBtn.disabled = false;
                promocodeBtn.classList.remove('applied');
            });
        });
    }
    
    // Функція для отримання CSRF токена
    function getCookie(name) {
        let cookieValue = null;
        if (document.cookie && document.cookie !== '') {
            const cookies = document.cookie.split(';');
            for (let i = 0; i < cookies.length; i++) {
                const cookie = cookies[i].trim();
                if (cookie.substring(0, name.length + 1) === (name + '=')) {
                    cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
                    break;
                }
            }
        }
        return cookieValue;
    }
    
    // Функція для оновлення цін зі знижкою
    function updatePricesWithDiscount(data) {
        const { final_price, discount_percent } = data;
        
        // Оновлюємо загальну ціну товарів
        const totalPriceElements = document.querySelectorAll('.basket__calculate-sum-products-cost, .basket__calculate-total-price-value');
        totalPriceElements.forEach(element => {
            element.textContent = final_price + ' грн.';
        });
        
        // Додаємо інформацію про знижку
        const calculateBlock = document.querySelector('.basket__calculate');
        if (calculateBlock) {
            // Перевіряємо чи вже є блок зі знижкою
            let discountBlock = calculateBlock.querySelector('.basket__calculate-discount');
            
            if (!discountBlock) {
                discountBlock = document.createElement('div');
                discountBlock.className = 'basket__calculate-discount basket_right_block';
                discountBlock.innerHTML = `
                    <p class="basket__calculate-discount-title">Знижка</p>
                    <p class="basket__calculate-discount-value">-${discount_percent}%</p>
                `;
                
                // Вставляємо блок зі знижкою після блоку з ціною товарів
                const sumProductsBlock = calculateBlock.querySelector('.basket__calculate-sum-products');
                sumProductsBlock.after(discountBlock);
            } else {
                discountBlock.querySelector('p:last-child').textContent = `-${discount_percent}%`;
            }
        }
    }
    
    // Відновлюємо застосований промокод при завантаженні сторінки
    const appliedPromocode = localStorage.getItem('applied_promocode');
    if (appliedPromocode && promocodeBtn && promocodeInput) {
        promocodeBtn.textContent = 'Застосовано';
        promocodeBtn.classList.add('applied');
        promocodeInput.value = appliedPromocode;
    }
}); 