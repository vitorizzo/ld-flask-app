document.addEventListener('DOMContentLoaded', function() {
    const menuItems = document.querySelectorAll('.menu-item');
    menuItems.forEach(item => {
        item.addEventListener('click', function() {
            const menuId = this.querySelector('.menu-id').textContent;
            loadMenuData(menuId);
        });
    });
});

function loadMenuData(menuId) {
    fetch(`/settings/menu/${menuId}`)
        .then(response => response.json())
        .then(data => {
            updateForm(data);
        });
}

function updateForm(data) {
    for (const [key, value] of Object.entries(data)) {
        const input = document.querySelector(`#${key}`);
        if (input) {
            input.value = value;
        }
    }
}