document.addEventListener('DOMContentLoaded', function() {
    initializeMenuManagement();

    function buildTree(items) {
      const byId = new Map();
      items.forEach(i => byId.set(i.id, { ...i, children: [] }));

      const roots = [];
      byId.forEach(node => {
        if (node.parent_id == null) {
          roots.push(node);
        } else {
          const parent = byId.get(node.parent_id);
          if (parent) parent.children.push(node);
          else roots.push(node); // fallback: orfano -> root
        }
      });

      // Ordina ricorsivamente per sort_order, poi id (stabile)
      function sortRec(nodes) {
        nodes.sort((a, b) => (a.sort_order ?? 0) - (b.sort_order ?? 0) || a.id - b.id);
        nodes.forEach(n => sortRec(n.children));
      }
      sortRec(roots);

      return roots;
    }

    function renderTree(nodes) {
      const ul = document.createElement("ul");
      ul.className = "menu-tree list-unstyled ms-2";
      ul.dataset.sortable = "1";

      nodes.forEach(n => {
        const li = document.createElement("li");
        li.className = "menu-node mb-1";
        li.dataset.id = n.id;

        // Riga “drag handle”
        const row = document.createElement("div");
        row.className = "d-flex align-items-center gap-2 p-2 border rounded";
        row.innerHTML = `
          <span class="menu-handle" style="cursor:grab;">☰</span>
          <span>${n.name ?? ("#" + n.id)}</span>
          <span class="badge bg-secondary ms-auto">w:${n.weight}</span>
        `;
        li.appendChild(row);

        if (n.children && n.children.length) {
          li.appendChild(renderTree(n.children));
        }

        ul.appendChild(li);
      });

      return ul;
    }

    function initNestedSortable(rootEl) {
      // Inizializza Sortable su tutti gli <ul data-sortable="1">
      const lists = rootEl.querySelectorAll('ul[data-sortable="1"]');
      lists.forEach(ul => {
        new Sortable(ul, {
          group: "menus",
          animation: 150,
          handle: ".menu-handle",
          fallbackOnBody: true,
          swapThreshold: 0.65,
          onEnd: () => {
            // Per ora: solo log. Salvataggio nello step successivo.
            console.log("Tree changed:", collectTree(rootEl));
          }
        });
      });
    }

    function collectTree(rootEl) {
      // Ritorna una lista di {id, parent_id, sort_order} calcolata dalla UI
      const result = [];
      function walk(ul, parentId) {
        const children = Array.from(ul.children).filter(el => el.matches("li.menu-node"));
        children.forEach((li, idx) => {
          const id = parseInt(li.dataset.id, 10);
          result.push({ id, parent_id: parentId, sort_order: idx });
          const childUl = li.querySelector(":scope > ul");
          if (childUl) walk(childUl, id);
        });
      }
      const rootUl = rootEl.querySelector("ul.menu-tree");
      if (rootUl) walk(rootUl, null);
      return result;
    }

    async function loadMenuStructureAndInitTree() {
      const treeHost = document.getElementById("menuTree");
      if (!treeHost) return;

      const res = await fetch("/settings/get_menu_structure");
      if (!res.ok) throw new Error("get_menu_structure failed: " + res.status);
      const items = await res.json();

      const roots = buildTree(items);
      treeHost.innerHTML = "";
      treeHost.appendChild(renderTree(roots));
      initNestedSortable(treeHost);
    }

    // Avvio
    document.addEventListener("DOMContentLoaded", () => {
      loadMenuStructureAndInitTree().catch(err => console.error(err));
    });

});

function initializeMenuManagement() {
    attachMenuItemListeners();
    setupFormSubmission();
    setupCancelButton();
    setupDragAndDrop();
    setupAddRemoveButtons();
}

function setupCancelButton() {
    const cancelButton = document.getElementById('cancelButton');
    cancelButton.addEventListener('click', function() {
        document.querySelector('form').reset();
    });
}

function updateMenuDisplay(updatedMenu) {
    fetch('/settings/get_menu_structure')
        .then(response => response.json())
        .then(menuStructure => {
            const centralSection = document.querySelector('.central-section ul');
            centralSection.innerHTML = buildMenuHTML(menuStructure);
        })
        .catch(error => console.error('Errore nel recupero della struttura del menu:', error));
}

function setupFormSubmission() {
    const form = document.querySelector('form');
    form.addEventListener('submit', handleFormSubmit);
}

function handleFormSubmit(e) {
    e.preventDefault();
    const formData = new FormData(e.target);

    fetch('/settings/update_menu', {
        method: 'POST',
        body: formData
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            updateMenuDisplay(data.updatedMenu);
            fetchAndUpdateMenuStructure();
        } else {
            throw new Error(data.error || 'Errore sconosciuto');
        }
    })
    .catch(error => {
        console.error('Errore durante l\'aggiornamento del menu:', error);
    });
}

function fetchAndUpdateMenuStructure() {
    fetch('/settings/get_menu_structure')
        .then(response => response.json())
        .then(menuStructure => {
            updateCentralSection(menuStructure);
        })
        .catch(error => console.error('Errore nel recupero della struttura del menu:', error));
}

function updateCentralSection(menuStructure) {
    const centralSection = document.querySelector('.central-section ul');
    centralSection.innerHTML = buildMenuHTML(menuStructure);
    attachMenuItemListeners();
}

function loadMenuData(menuId) {
    fetch(`/settings/menu/${menuId}`)
        .then(response => response.json())
        .then(data => {
            const form = document.querySelector('form');
            for (const [key, value] of Object.entries(data)) {
                const input = form.elements[key];
                if (input) input.value = value;
            }
            form.elements['menu_id'].value = menuId;
        })
        .catch(error => console.error('Errore nel caricamento dei dati del menu:', error));
}

function initializeMenuManagement() {
    attachMenuItemListeners();
    setupFormSubmission();
    setupCancelButton();
    setupAddRemoveButtons();
    setupDragAndDrop();
}

function attachMenuItemListeners() {
    document.querySelector('.central-section').addEventListener('click', function(event) {
        const menuItem = event.target.closest('.menu-item.clickable');
        if (menuItem) {
            const menuId = menuItem.querySelector('.menu-id').textContent;
            loadMenuData(menuId);
        }
    });
}

function handleMenuItemClick(event) {
    const menuItem = event.target.closest('.menu-item.clickable');
    if (menuItem) {
        const menuId = menuItem.querySelector('.menu-id').textContent;
        loadMenuData(menuId);
    }
}

function updateForm(data) {
    document.getElementById('menu_id').value = data.id;
    for (const [key, value] of Object.entries(data)) {
        const input = document.querySelector(`#${key}`);
        if (input) {
            input.value = value;
        }
    }
}

function buildMenuHTML(menuItems) {
    return menuItems.map(item => `
        <li class="menu-item clickable" draggable="true" data-id="${item.id}">
            <span class="menu-name">${item.name}</span> (<span class="menu-id">${item.id}</span>)
            <button class="add-item">+</button>
            <button class="remove-item">-</button>
            ${item.children ? `<ul>${buildMenuHTML(item.children)}</ul>` : ''}
        </li>
    `).join('');
}

function setupDragAndDrop() {
    const menuList = document.querySelector('.central-section ul');
    menuList.addEventListener('dragstart', handleDragStart);
    menuList.addEventListener('dragover', handleDragOver);
    menuList.addEventListener('drop', handleDrop);
}

function handleDragStart(e) {
    e.dataTransfer.setData('text/plain', e.target.dataset.id);
}

function handleDragOver(e) {
    e.preventDefault();
}

function handleDrop(e) {
    e.preventDefault();
    const draggedId = e.dataTransfer.getData('text');
    const dropTarget = e.target.closest('.menu-item');
    if (dropTarget && draggedId !== dropTarget.dataset.id) {
        // Implementa qui la logica per aggiornare l'ordine dei menu nel backend
        fetchAndUpdateMenuStructure();
    }
}

function setupAddRemoveButtons() {
    document.querySelector('.central-section').addEventListener('click', function(e) {
        if (e.target.classList.contains('add-item')) {
            const parentId = e.target.closest('.menu-item').dataset.id;
            addNewMenuItem(parentId);
        } else if (e.target.classList.contains('remove-item')) {
            const menuId = e.target.closest('.menu-item').dataset.id;
            removeMenuItem(menuId);
        }
    });
}

function addNewMenuItem(parentId) {
    const newName = prompt('Inserisci il nome del nuovo menu item:');
    if (newName) {
        // Implementa la chiamata al backend per aggiungere il nuovo item
        fetch('/settings/add_menu_item', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({ parent_id: parentId, name: newName }),
        })
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                fetchAndUpdateMenuStructure();
            } else {
                throw new Error(data.error || 'Errore sconosciuto');
            }
        });
    }
}

function removeMenuItem(menuId) {
    if (confirm('Sei sicuro di voler rimuovere questo menu item? Questa azione rimuoverà anche tutti i sotto-menu.')) {
        // Implementa la chiamata al backend per rimuovere l'item
        fetch('/settings/remove_menu_item', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({ menu_id: menuId }),
        })
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                fetchAndUpdateMenuStructure();
            } else {
                throw new Error(data.error || 'Errore sconosciuto');
            }
        });
    }
}

    const alertDiv = document.createElement('div');
    alertDiv.className = `alert alert-${category} alert-dismissible fade show`;
    alertDiv.setAttribute('role', 'alert');
    alertDiv.innerHTML = `
        ${message}
        <button type="button" class="btn-close" data-bs-dismiss="alert" aria-label="Close"></button>
    `;

    flashContainer.appendChild(alertDiv);

    setTimeout(() => {
        alertDiv.remove();
    }, 5000);
}
