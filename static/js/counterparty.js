// JS-файл для взаимодействия с API контрагентов

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
        customerType: document.getElementById('customerType')?.value || ''
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
        alert('Помилка з'єднання з сервером');
    });
}
