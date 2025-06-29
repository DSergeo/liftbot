// JS-файл для взаємодії з API контрагентів

function saveCounterparty() {
    const counterpartyData = {
        companyName: document.getElementById('companyName')?.value || '',
        edrpou: document.getElementById('edrpou')?.value || '',
        iban: document.getElementById('iban')?.value || '',
        bank: document.getElementById('bank')?.value || '',
        mfo: document.getElementById('mfo')?.value || '',
        director: document.getElementById('director')?.value || '',
        accountant: document.getElementById('accountant')?.value || '',
        address: document.getElementById('address')?.value || '',
        phone: document.getElementById('phone')?.value || '',
        email: document.getElementById('email')?.value || '',
        vatNumber: document.getElementById('vatNumber')?.value || '',
        taxNumber: document.getElementById('taxNumber')?.value || '',
        certificateNumber: document.getElementById('certificateNumber')?.value || '',
        certificateDate: document.getElementById('certificateDate')?.value || '',
        legalForm: document.getElementById('legalForm')?.value || '',
        customerType: document.getElementById('customerType')?.value || '',
        legalAddress: document.getElementById('legalAddress')?.value || '',
        city: document.getElementById('city')?.value || '',
        region: document.getElementById('region')?.value || '',
        postalCode: document.getElementById('postalCode')?.value || '',
        website: document.getElementById('website')?.value || '',
        industry: document.getElementById('industry')?.value || '',
        description: document.getElementById('description')?.value || ''
    };

    fetch('/api/counterparties', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        },
        body: JSON.stringify(counterpartyData)
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            alert('Контрагента збережено успішно!');
            location.reload();
        } else {
            console.error('Error saving counterparty:', data.error);
            alert('Помилка при збереженні: ' + (data.error || 'Невідома помилка'));
        }
    })
    .catch(error => {
        console.error('Error saving counterparty:', error);
        alert('Помилка з\'єднання з сервером');
    });
}

function fillCounterpartyForm(counterparty) {
    document.getElementById('counterpartyId').value = counterparty.id || '';
    document.getElementById('companyName').value = counterparty.companyName || '';
    document.getElementById('edrpou').value = counterparty.edrpou || '';
    document.getElementById('iban').value = counterparty.iban || '';
    document.getElementById('bank').value = counterparty.bank || '';
    document.getElementById('mfo').value = counterparty.mfo || '';
    document.getElementById('director').value = counterparty.director || '';
    document.getElementById('accountant').value = counterparty.accountant || '';
    document.getElementById('address').value = counterparty.address || '';
    document.getElementById('phone').value = counterparty.phone || '';
    document.getElementById('email').value = counterparty.email || '';
    document.getElementById('vatNumber').value = counterparty.vatNumber || '';
    document.getElementById('taxNumber').value = counterparty.taxNumber || '';
    document.getElementById('certificateNumber').value = counterparty.certificateNumber || '';
    document.getElementById('certificateDate').value = counterparty.certificateDate || '';
    document.getElementById('legalForm').value = counterparty.legalForm || '';
    document.getElementById('customerType').value = counterparty.customerType || '';
    document.getElementById('legalAddress').value = counterparty.legalAddress || '';
    document.getElementById('city').value = counterparty.city || '';
    document.getElementById('region').value = counterparty.region || '';
    document.getElementById('postalCode').value = counterparty.postalCode || '';
    document.getElementById('website').value = counterparty.website || '';
    document.getElementById('industry').value = counterparty.industry || '';
    document.getElementById('description').value = counterparty.description || '';
    // Корректно виставляем значения для select (с учетом наличия опції)
    const typeSelect = document.getElementById('counterpartyType');
    if (counterparty.counterpartyType && typeSelect) {
        for (let i = 0; i < typeSelect.options.length; i++) {
            if (typeSelect.options[i].value === counterparty.counterpartyType) {
                typeSelect.selectedIndex = i;
                break;
            }
        }
    }
    const statusSelect = document.getElementById('status');
    if (counterparty.status && statusSelect) {
        for (let i = 0; i < statusSelect.options.length; i++) {
            if (statusSelect.options[i].value === counterparty.status) {
                statusSelect.selectedIndex = i;
                break;
            }
        }
    }
}

// Для совместимости: если используется editCounterparty(index), то заменить вызов заполнения формы
function editCounterparty(index) {
    const counterparty = counterparties[index];
    fillCounterpartyForm(counterparty);
    document.getElementById('createCounterpartyModalLabel').textContent = 'Редагувати контрагента';
    const modal = new bootstrap.Modal(document.getElementById('createCounterpartyModal'));
    modal.show();
}
