// Inventory Management JavaScript
class InventoryManager {
    constructor() {
        this.currentPage = 1;
        this.perPage = 20;
        this.totalPages = 1;
        this.filters = {
            search: '',
            category: '',
            status: ''
        };
        this.initialData = window.initialData || {};
        this.setupEventListeners();
        this.initializePage();
    }

    setupEventListeners() {
        // Search and filter events
        document.getElementById('searchInput')?.addEventListener('input', debounce(() => {
            this.filters.search = document.getElementById('searchInput').value;
            this.currentPage = 1; // Reset to first page on filter change
            this.loadInventoryItems();
        }, 300));

        document.getElementById('categoryFilter')?.addEventListener('change', () => {
            this.filters.category = document.getElementById('categoryFilter').value;
            this.currentPage = 1;
            this.loadInventoryItems();
        });

        document.getElementById('stockFilter')?.addEventListener('change', () => {
            this.filters.status = document.getElementById('stockFilter').value;
            this.currentPage = 1;
            this.loadInventoryItems();
        });

        document.getElementById('clearFilters')?.addEventListener('click', () => {
            this.clearFilters();
        });

        // Add item form
        document.getElementById('addItemForm')?.addEventListener('submit', (e) => {
            e.preventDefault();
            this.addInventoryItem();
        });

        // Edit item form
        document.getElementById('editItemForm')?.addEventListener('submit', (e) => {
            e.preventDefault();
            const itemId = e.target.dataset.itemId;
            this.updateItem(itemId);
        });

        // Adjust stock form
        document.getElementById('adjustStockForm')?.addEventListener('submit', (e) => {
            e.preventDefault();
            const itemId = e.target.dataset.itemId;
            this.submitStockAdjustment(itemId);
        });

        // Select all checkbox
        document.getElementById('selectAll')?.addEventListener('change', (e) => {
            const checkboxes = document.querySelectorAll('.item-checkbox');
            checkboxes.forEach(checkbox => checkbox.checked = e.target.checked);
        });
    }

    initializePage() {
        
        // Check for category query parameter and set filter
        const urlParams = new URLSearchParams(window.location.search);
        const categoryId = urlParams.get('category');
        if (categoryId) {
            this.filters.category = categoryId;
            const categoryFilter = document.getElementById('categoryFilter');
            if (categoryFilter) categoryFilter.value = categoryId;
        }

        
        //this.renderInventoryTable(this.initialData.inventory_items || []);
        
        
        // Load items based on category filter
        if (categoryId) {
            this.loadInventoryItems();
        } else {
            this.renderInventoryTable(this.initialData.inventory_items || []);
            // Populate initial data
        this.updateStats(this.initialData.stats || {});
        this.populateCategories(this.initialData.categories || []);
         // set pagination
       this.loadInventoryPagination();
        }
       
    }

    // specifically for page pagination
    async loadInventoryPagination() {
        try {
            const queryParams = new URLSearchParams({
                page: this.currentPage,
                per_page: this.perPage,
                ...this.filters
            });

            const response = await fetch(`/api/v1/inventory/list/?${queryParams}`, {
                headers: {
                    'Authorization': `Token ${authTokenFromView}`,
                    'X-CSRFToken': this.getCsrfToken()
                }
            });

            if (!response.ok) throw new Error('Failed to load inventory items');

            const data = await response.json();
            this.totalPages = data.total_pages;
            this.updatePagination();
           
        } catch (error) {
            console.error('Error updating pagination:', error);
           
        }
    }

    async loadInventoryItems() {
        try {
            const queryParams = new URLSearchParams({
                page: this.currentPage,
                per_page: this.perPage,
                ...this.filters
            });

            const response = await fetch(`/api/v1/inventory/list/?${queryParams}`, {
                headers: {
                    'Authorization': `Token ${authTokenFromView}`,
                    'X-CSRFToken': this.getCsrfToken()
                }
            });

            if (!response.ok) throw new Error('Failed to load inventory items');

            const data = await response.json();
            this.totalPages = data.total_pages;
            this.renderInventoryTable(data.items);
            this.updatePagination();
            this.updateStats(data.stats || {});
        } catch (error) {
            console.error('Error loading inventory items:', error);
            this.showToast('Failed to load inventory items', 'error');
        }
    }

    renderInventoryTable(items) {
        const tbody = document.getElementById('inventoryTableBody');
        if (!tbody) return;

        tbody.innerHTML = items.map(item => `
            <tr>
                <td>
                    <input type="checkbox" class="form-check-input item-checkbox" value="${item.id}">
                </td>
                <td>
                    <div class="d-flex align-items-center">
                        <div>
                            <h6 class="mb-0">${item.name}</h6>
                           
                        </div>
                    </div>
                </td>
                <td><code>${item.sku}</code></td>
                <td>
                    <span class="badge bg-light text-dark">${item.category}</span>
                </td>
                <td>${item.size || '-'}</td>
                <td>₦${parseFloat(item.price).toLocaleString()}</td>
                <td>
                    <span class="fw-bold ${item.quantity <= item.min_stock ? 'text-danger' : 'text-success'}">
                        ${item.quantity}
                    </span>
                </td>
                <td>${this.getStatusBadge(item.status)}</td>
                <td>
                    <div class="btn-group" role="group">
                        <button class="btn btn-sm btn-outline-primary edit-item-btn" 
                                data-bs-toggle="modal" 
                                data-bs-target="#editItemModal"
                                data-item='${JSON.stringify(item)}'
                                title="Edit">
                            <i class="fas fa-edit"></i>
                        </button>
                        <button class="btn btn-sm btn-outline-success adjust-stock-btn" 
                                data-bs-toggle="modal" 
                                data-bs-target="#adjustStockModal"
                                data-item='${JSON.stringify(item)}'
                                title="Adjust Stock">
                            <i class="fas fa-plus-minus"></i>
                        </button>
                        <button class="btn btn-sm btn-outline-danger" 
                                onclick="inventoryManager.deleteItem(${item.id})" 
                                title="Delete">
                            <i class="fas fa-trash"></i>
                        </button>
                    </div>
                </td>
            </tr>
        `).join('');

        // Update pagination info
        document.getElementById('itemsShown').textContent = items.length;
        document.getElementById('totalItemsShown').textContent = this.totalPages * this.perPage;

        // Add event listeners for the new buttons
        this.setupModalButtons();
    }

    setupModalButtons() {
        // Edit modal buttons
        document.querySelectorAll('.edit-item-btn').forEach(button => {
            button.addEventListener('click', (e) => {
                const item = JSON.parse(e.target.closest('button').dataset.item);
                this.populateEditForm(item);
            });
        });

        // Adjust stock modal buttons
        document.querySelectorAll('.adjust-stock-btn').forEach(button => {
            button.addEventListener('click', (e) => {
                const item = JSON.parse(e.target.closest('button').dataset.item);
                document.getElementById('adjustStockItemName').textContent = item.name;
                document.getElementById('adjustStockCurrentQuantity').textContent = item.quantity;
                document.getElementById('adjustStockForm').dataset.itemId = item.id;
            });
        });
    }

    updateStats(stats) {
        document.getElementById('totalItems').textContent = stats.total_items || 0;
        document.getElementById('totalValue').textContent = `₦${parseFloat(stats.total_value || 0).toLocaleString()}`;
        document.getElementById('lowStockCount').textContent = stats.low_stock_count || 0;
        document.getElementById('categoriesCount').textContent = stats.categories_count || 0;
    }

    populateCategories(categories) {
        const categoryFilter = document.getElementById('categoryFilter');
        const addItemCategory = document.getElementById('itemCategory');
        const editItemCategory = document.getElementById('editItemCategory');
        
        if (!categoryFilter || !addItemCategory || !editItemCategory) return;

        const options = categories.map(cat => 
            `<option value="${cat.id}">${cat.name} (${cat.item_count})</option>`
        ).join('');
        
        const defaultOption = '<option value="">All Categories</option>';
        const selectOption = '<option value="">Select Category</option>';
        
        categoryFilter.innerHTML = defaultOption + options;
        addItemCategory.innerHTML = selectOption + options;
        editItemCategory.innerHTML = selectOption + options;
    }

    async refreshCategories() {
        try {
            const response = await fetch('/api/v1/category/list-count/', {
                headers: {
                    'Authorization': `Token ${authTokenFromView}`,
                    'X-CSRFToken': this.getCsrfToken()
                }
            });

            if (!response.ok) throw new Error('Failed to load categories');
            const categories = await response.json();
            this.populateCategories(categories);
        } catch (error) {
            console.error('Error refreshing categories:', error);
        }
    }

    updatePagination() {
        const pagination = document.querySelector('.pagination');
        if (!pagination) return;

        let html = `
            <li class="page-item ${this.currentPage === 1 ? 'disabled' : ''}">
                <a class="page-link" href="#" data-page="${this.currentPage - 1}">Previous</a>
            </li>
        `;

        for (let i = 1; i <= this.totalPages; i++) {
            html += `
                <li class="page-item ${i === this.currentPage ? 'active' : ''}">
                    <a class="page-link" href="#" data-page="${i}">${i}</a>
                </li>
            `;
        }

        html += `
            <li class="page-item ${this.currentPage === this.totalPages ? 'disabled' : ''}">
                <a class="page-link" href="#" data-page="${this.currentPage + 1}">Next</a>
            </li>
        `;

        pagination.innerHTML = html;

        // Add click handlers
        pagination.querySelectorAll('.page-link').forEach(link => {
            link.addEventListener('click', (e) => {
                e.preventDefault();
                const page = parseInt(e.target.dataset.page);
                if (page && page !== this.currentPage) {
                    this.currentPage = page;
                    this.loadInventoryItems();
                }
            });
        });
    }

    async addInventoryItem() {
        const form = document.getElementById('addItemForm');
        if (!form) return;

        const formData = new FormData(form);
        const data = {
            name: formData.get('itemName'),
            category: formData.get('itemCategory'),
            size: formData.get('itemSize'),
            price: parseFloat(formData.get('itemPrice')),
            quantity: parseInt(formData.get('itemQuantity')),
            min_stock: parseInt(formData.get('itemMinStock')),
            description: formData.get('itemDescription')
        };

        try {
            const response = await fetch('/api/v1/inventory/add/', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'Authorization': `Token ${authTokenFromView}`,
                    'X-CSRFToken': this.getCsrfToken()
                },
                body: JSON.stringify(data)
            });

            if (!response.ok) throw new Error('Failed to add item');

            const result = await response.json();
            this.showToast('Item added successfully', 'success');
            bootstrap.Modal.getInstance(document.getElementById('addItemModal')).hide();
            form.reset();
            await this.loadInventoryItems();
            await this.refreshStats();
            await this.refreshCategories();
        } catch (error) {
            console.error('Error adding item:', error);
            this.showToast('Failed to add item', 'error');
        }
    }

    async editItem(itemId) {
        try {
            const response = await fetch(`/api/v1/inventory/${itemId}/update/`, {
                headers: {
                    'Authorization': `Token ${authTokenFromView}`,
                    'X-CSRFToken': this.getCsrfToken()
                }
            });

            if (!response.ok) throw new Error('Failed to load item details');

            const item = await response.json();
            this.populateEditForm(item);
            new bootstrap.Modal(document.getElementById('editItemModal')).show();
        } catch (error) {
            console.error('Error loading item details:', error);
            this.showToast('Failed to load item details', 'error');
        }
    }

    populateEditForm(item) {
        const form = document.getElementById('editItemForm');
        if (!form) return;

        form.querySelector('#editItemName').value = item.name;
        form.querySelector('#editItemCategory').value = item.category;
        form.querySelector('#editItemSize').value = item.size || '';
        form.querySelector('#editItemPrice').value = item.price;
        form.querySelector('#editItemQuantity').value = item.quantity;
        form.querySelector('#editItemMinStock').value = item.min_stock;
        form.querySelector('#editItemDescription').value = item.description || '';
        form.dataset.itemId = item.id;
    }

    async updateItem(itemId) {
        const form = document.getElementById('editItemForm');
        if (!form) return;

        const formData = new FormData(form);
        const data = {
            name: formData.get('itemName'),
            category: formData.get('itemCategory'),
            size: formData.get('itemSize'),
            price: parseFloat(formData.get('itemPrice')),
            quantity: parseInt(formData.get('itemQuantity')),
            min_stock: parseInt(formData.get('itemMinStock')),
            description: formData.get('itemDescription')
        };

        try {
            const response = await fetch(`/api/v1/inventory/${itemId}/update/`, {
                method: 'PUT',
                headers: {
                    'Content-Type': 'application/json',
                    'Authorization': `Token ${authTokenFromView}`,
                    'X-CSRFToken': this.getCsrfToken()
                },
                body: JSON.stringify(data)
            });

            if (!response.ok) throw new Error('Failed to update item');

            const result = await response.json();
            this.showToast('Item updated successfully', 'success');
            bootstrap.Modal.getInstance(document.getElementById('editItemModal')).hide();
            await Promise.all([
                this.loadInventoryItems(),
                this.refreshStats(),
               
            ]);
        } catch (error) {
            console.error('Error updating item:', error);
            this.showToast('Failed to update item', 'error');
        }
    }

    async submitStockAdjustment(itemId) {
        const form = document.getElementById('adjustStockForm');
        if (!form) return;

        const quantity = parseInt(document.getElementById('adjustStockQuantity').value);
        const adjustmentType = document.getElementById('adjustmentType').value;
        const finalChange = adjustmentType === 'remove' ? -quantity : quantity;

        try {
            const response = await fetch(`/api/v1/inventory/${itemId}/adjust-stock/`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'Authorization': `Token ${authTokenFromView}`,
                    'X-CSRFToken': this.getCsrfToken()
                },
                body: JSON.stringify({ quantity_change: finalChange })
            });

            if (!response.ok) throw new Error('Failed to adjust stock');

            const result = await response.json();
            this.showToast('Stock adjusted successfully', 'success');
            bootstrap.Modal.getInstance(document.getElementById('adjustStockModal')).hide();
            form.reset();
            await Promise.all([
                this.loadInventoryItems(),
                this.refreshStats(),
                
            ]);
        } catch (error) {
            console.error('Error adjusting stock:', error);
            this.showToast('Failed to adjust stock', 'error');
        }
    }

    async deleteItem(itemId) {
        if (!confirm('Are you sure you want to delete this item?')) return;

        try {
            const response = await fetch(`/api/v1/inventory/${itemId}/delete/`, {
                method: 'DELETE',
                headers: {
                    'Authorization': `Token ${authTokenFromView}`,
                    'X-CSRFToken': this.getCsrfToken()
                }
            });

            if (!response.ok) throw new Error('Failed to delete item');

            this.showToast('Item deleted successfully', 'success');
            await Promise.all([
                this.loadInventoryItems(),
                this.refreshStats(),
                this.refreshCategories()
            ]);
        } catch (error) {
            console.error('Error deleting item:', error);
            this.showToast('Failed to delete item', 'error');
        }
    }

    async adjustStock(itemId) {
        try {
            const response = await fetch(`/api/v1/inventory/${itemId}/update/`, {
                headers: {
                    'Authorization': `Token ${authTokenFromView}`,
                    'X-CSRFToken': this.getCsrfToken()
                }
            });

            if (!response.ok) throw new Error('Failed to load item details');

            const item = await response.json();
            document.getElementById('adjustStockItemName').textContent = item.name;
            document.getElementById('adjustStockCurrentQuantity').textContent = item.quantity;
            document.getElementById('adjustStockForm').dataset.itemId = itemId;
            new bootstrap.Modal(document.getElementById('adjustStockModal')).show();
        } catch (error) {
            console.error('Error loading item details:', error);
            this.showToast('Failed to load item details', 'error');
        }
    }

    async loadStats() {
        try {
            const response = await fetch('/api/v1/inventory/stats/', {
                headers: {
                    'Authorization': `Token ${authTokenFromView}`,
                    'X-CSRFToken': this.getCsrfToken()
                }
            });

            if (!response.ok) throw new Error('Failed to load stats');
            const stats = await response.json();
            this.updateStats(stats);
        } catch (error) {
            console.error('Error loading stats:', error);
        }
    }

    async refreshStats() {
        try {
            const response = await fetch('/api/v1/inventory/stats/', {
                headers: {
                    'Authorization': `Token ${authTokenFromView}`,
                    'X-CSRFToken': this.getCsrfToken()
                }
            });

            if (!response.ok) throw new Error('Failed to load stats');
            const stats = await response.json();
            this.updateStats(stats);
        } catch (error) {
            console.error('Error refreshing stats:', error);
        }
    }

    clearFilters() {
        document.getElementById('searchInput').value = '';
        document.getElementById('categoryFilter').value = '';
        document.getElementById('stockFilter').value = '';
        this.filters = {
            search: '',
            category: '',
            status: ''
        };
        this.currentPage = 1;
        this.loadInventoryItems();
    }

    getStatusBadge(status) {
        const badges = {
            'in_stock': '<span class="badge bg-success">In Stock</span>',
            'low_stock': '<span class="badge bg-warning">Low Stock</span>',
            'out_of_stock': '<span class="badge bg-danger">Out of Stock</span>'
        };
        return badges[status] || '<span class="badge bg-secondary">Unknown</span>';
    }

    getCsrfToken() {
        return document.querySelector('[name=csrfmiddlewaretoken]').value;
    }

    showToast(message, type = 'info') {
        const toast = document.createElement('div');
        toast.className = `toast align-items-center text-bg-${type} border-0`;
        toast.setAttribute('role', 'alert');
        toast.innerHTML = `
            <div class="d-flex">
                <div class="toast-body">${message}</div>
                <button type="button" class="btn-close btn-close-white me-2 m-auto" data-bs-dismiss="toast"></button>
            </div>
        `;

        const container = document.getElementById('toastContainer') || this.createToastContainer();
        container.appendChild(toast);

        const bsToast = new bootstrap.Toast(toast);
        bsToast.show();

        toast.addEventListener('hidden.bs.toast', () => toast.remove());
    }

    createToastContainer() {
        const container = document.createElement('div');
        container.id = 'toastContainer';
        container.className = 'toast-container position-fixed top-0 end-0 p-3';
        document.body.appendChild(container);
        return container;
    }
}

// Utility function for debouncing
function debounce(func, wait) {
    let timeout;
    return function executedFunction(...args) {
        const later = () => {
            clearTimeout(timeout);
            func(...args);
        };
        clearTimeout(timeout);
        timeout = setTimeout(later, wait);
    };
}

// Initialize inventory manager when DOM is loaded
document.addEventListener('DOMContentLoaded', () => {
    window.inventoryManager = new InventoryManager();
}); 