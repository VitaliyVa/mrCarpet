def cart_total_price(cart):
    total_price = sum([cp.cart_product_total_price() for cp in cart.cart_products.all()])
    return total_price