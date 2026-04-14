export function formatCurrency(value) {
    return "₹" + Number(value || 0).toFixed(2);
}
