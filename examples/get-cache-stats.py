import radar

c = radar.product.Client(port=50000)
r = c.stats()
print(r)
