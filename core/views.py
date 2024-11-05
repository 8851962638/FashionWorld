from django.shortcuts import render, redirect, get_object_or_404
from core.forms import CheckoutForm, ProductForm
from django.contrib import messages
from core.models import Product, Order, OrderItem, CheckoutAddress
from django.utils import timezone
from django.conf import settings
from django.http import HttpResponse
from django.views.decorators.csrf import csrf_exempt
import razorpay
import logging
from xhtml2pdf import pisa
from django.template.loader import get_template

# Initialize Razorpay client
razorpay_client = razorpay.Client(auth=(settings.RAZORPAY_ID, settings.RAZORPAY_SECRET))

logger = logging.getLogger(__name__)

def index(request):
    products = Product.objects.all()
    return render(request, "core/index.html", {"products": products})

def orderlist(request):
    order = Order.objects.filter(user=request.user, ordered=False).first()
    if order:
        return render(request, "core/orderlist.html", {"order": order})
    return render(request, "core/orderlist.html", {"message": "Your Cart is Empty"})

def add_product(request):
    if request.method == "POST":
        form = ProductForm(request.POST, request.FILES)
        if form.is_valid():
            form.save()
            messages.success(request, "Product Added Successfully")
            return redirect("/")
        else:
            messages.info(request, "Product is not Added, Try Again")
    else:
        form = ProductForm()
    return render(request, "core/add_product.html", {"form": form})

def product_desc(request, pk):
    product = get_object_or_404(Product, pk=pk)
    return render(request, "core/product_desc.html", {"product": product})

def add_to_cart(request, pk):
    product = get_object_or_404(Product, pk=pk)
    order_item, created = OrderItem.objects.get_or_create(product=product, user=request.user, ordered=False)
    order = Order.objects.filter(user=request.user, ordered=False).first()

    if order:
        if order.items.filter(product__pk=pk).exists():
            order_item.quantity += 1
            order_item.save()
            messages.info(request, "Added Quantity Item")
        else:
            order.items.add(order_item)
            messages.info(request, "Item added to Cart")
    else:
        ordered_date = timezone.now()
        order = Order.objects.create(user=request.user, ordered_date=ordered_date)
        order.items.add(order_item)
        messages.info(request, "Item added to Cart")
    
    return redirect("product_desc", pk=pk)

def add_item(request, pk):
    product = get_object_or_404(Product, pk=pk)
    order_item, created = OrderItem.objects.get_or_create(product=product, user=request.user, ordered=False)
    order = Order.objects.filter(user=request.user, ordered=False).first()

    if order:
        if order.items.filter(product__pk=pk).exists():
            if order_item.quantity < product.product_available_count:
                order_item.quantity += 1
                order_item.save()
                messages.info(request, "Added Quantity Item")
            else:
                messages.info(request, "Sorry! Product is out of Stock")
        else:
            order.items.add(order_item)
            messages.info(request, "Item added to Cart")
    else:
        ordered_date = timezone.now()
        order = Order.objects.create(user=request.user, ordered_date=ordered_date)
        order.items.add(order_item)
        messages.info(request, "Item added to Cart")
    
    return redirect("product_desc", pk=pk)

def remove_item(request, pk):
    item = get_object_or_404(Product, pk=pk)
    order = Order.objects.filter(user=request.user, ordered=False).first()

    if order and order.items.filter(product__pk=pk).exists():
        order_item = OrderItem.objects.filter(product=item, user=request.user, ordered=False).first()
        if order_item.quantity > 1:
            order_item.quantity -= 1
            order_item.save()
        else:
            order_item.delete()
        messages.info(request, "Item quantity was updated")
    else:
        messages.info(request, "This item is not in your cart")
    
    return redirect("orderlist")

def checkout_page(request):
    if CheckoutAddress.objects.filter(user=request.user).exists():
        return render(request, "core/checkout_address.html", {"payment_allow": "allow"})
    
    if request.method == "POST":
        form = CheckoutForm(request.POST)
        if form.is_valid():
            street_address = form.cleaned_data.get("street_address")
            apartment_address = form.cleaned_data.get("apartment_address")
            country = form.cleaned_data.get("country")
            zip_code = form.cleaned_data.get("zip")

            CheckoutAddress.objects.create(
                user=request.user,
                street_address=street_address,
                apartment_address=apartment_address,
                country=country,
                zip_code=zip_code,
            )
            return render(request, "core/checkout_address.html", {"payment_allow": "allow"})
    
    form = CheckoutForm()
    return render(request, "core/checkout_address.html", {"form": form})
def payment(request):
    try:
        order = Order.objects.get(user=request.user, ordered=False)
        address = CheckoutAddress.objects.get(user=request.user)
        order_amount = int(order.get_total_price() * 100)  # Amount in paise
        order_currency = "INR"
        order_receipt = str(order.id)
        notes = {
            "street_address": address.street_address,
            "apartment_address": address.apartment_address,
            "country": address.country.name,
            "zip": address.zip_code,
        }
        
        # Create an order with Razorpay
        razorpay_order = razorpay_client.order.create(
            data={
                "amount": order_amount,  # Amount in paise
                "currency": order_currency,  # Currency code
                "receipt": order_receipt,  # Receipt id (optional)
                "notes": notes,  # Additional notes (optional)
                "payment_capture": 1,  # Automatically capture payment
                # Optional fields (uncomment if needed)
                # "partial_payment": False,  # Allow partial payments (optional)
                # "first_payment_min_amount": 0  # Minimum amount for first partial payment (optional)
            }
        )

        # Check for success response
        if razorpay_order.get('status') == 'created':
            order.razorpay_order_id = razorpay_order["id"]
            order.save()

            return render(
                request,
                "core/paymentsummaryrazorpay.html",
                {
                    "order": order,
                    "order_id": razorpay_order["id"],
                    "orderId": order.order_id,
                    "final_price": order_amount / 100,  # Convert back to rupees for display
                    "razorpay_merchant_id": settings.RAZORPAY_ID,
                },
            )
        else:
            messages.error(request, "Failed to create order with Razorpay.")
            return redirect("orderlist")

    except Exception as e:
        logger.error(f"Exception occurred while creating Razorpay order: {e}")
        return HttpResponse("Error Occurred")

def render_pdf_view(request):
    order_id = request.GET.get("order_id")
    order_db = Order.objects.get(razorpay_order_id=order_id)
    checkout_address = CheckoutAddress.objects.get(user=request.user)
    amount = order_db.get_total_price() * 100
    payment_id = order_db.razorpay_payment_id
    payment_status = razorpay_client.payment.fetch(payment_id)
    template_path = 'invoice/invoice.html'
    context = {
        "order": order_db,
        "payment_status": payment_status,
        "checkout_address": checkout_address
    }

    response = HttpResponse(content_type='application/pdf')
    response['Content-Disposition'] = 'attachment; filename="report.pdf"'
    template = get_template(template_path)
    html = template.render(context)

    pisa_status = pisa.CreatePDF(html, dest=response)
    if pisa_status.err:
        return HttpResponse('We had some errors <pre>' + html + '</pre>')
    return response

@csrf_exempt
def handlerequest(request):
    if request.method == "POST":
        try:
            payment_id = request.POST.get("razorpay_payment_id", "")
            order_id = request.POST.get("razorpay_order_id", "")
            signature = request.POST.get("razorpay_signature", "")
            
            logger.info(f"Payment ID: {payment_id}, Order ID: {order_id}, Signature: {signature}")

            params_dict = {
                "razorpay_order_id": porder_9A33XWu170gUtm,
                "razorpay_payment_id": pay_29QQoUBi66xm2f,
                "razorpay_signature": "9ef4dffbfd84f1318f6739a3ce19f9d85851857ae648f114332d8401e0949a3d",
            }

            try:
                order_db = Order.objects.get(razorpay_order_id=order_id)
                logger.info("Order found in database.")
            except Order.DoesNotExist:
                logger.error("Order not found in database.")
                return HttpResponse("Order Not found")

            order_db.razorpay_payment_id = payment_id
            order_db.razorpay_signature = signature
            order_db.save()

            try:
                result = razorpay_client.utility.verify_payment_signature(params_dict)
                logger.info("Signature verification result: %s", result)
            except razorpay.errors.SignatureVerificationError as e:
                logger.error(f"Signature verification error: {e}")
                return HttpResponse("Signature verification failed")

            if result:
                amount = order_db.get_total_price() * 100
                try:
                    payment_status = razorpay_client.payment.capture(payment_id, amount)
                    logger.info("Payment captured: %s", payment_status)
                except razorpay.errors.RazorpayError as e:
                    logger.error(f"Error in payment capture: {e}")
                    return HttpResponse("Payment capture failed")

                if payment_status.get("status") == "captured":
                    order_db.ordered = True
                    order_db.save()
                    checkout_address = CheckoutAddress.objects.get(user=request.user)
                    request.session[
                        "order_complete"
                    ] = "Your Order is Successfully Placed, You will receive your order within 5-7 working days"
                    return render(request, "invoice/invoice.html", {"order": order_db, "payment_status": payment_status, "checkout_address": checkout_address})
                else:
                    logger.error("Payment status not captured.")
                    order_db.ordered = False
                    order_db.save()
                    request.session[
                        "order_failed"
                    ] = "Unfortunately your order could not be placed, try again!"
                    return redirect("/")
            else:
                logger.error("Result verification failed.")
                order_db.ordered = False
                order_db.save()
                return render(request, "core/paymentfailed.html")
        except Exception as e:
            logger.error(f"Exception occurred: {e}")
            return HttpResponse("Error Occurred")

def invoice(request):
    return render(request, "invoice/invoice.html")

def payment_success(request):
    payment_id = request.GET.get('razorpay_payment_id')
    order_id = request.GET.get('razorpay_order_id')
    signature = request.GET.get('razorpay_signature')
    return render(request, 'core/payment_success.html', {
        'payment_id': payment_id,
        'order_id': order_id,
        'signature': signature
    })

def payment_failure(request):
    return render(request, 'core/payment_failure.html')
