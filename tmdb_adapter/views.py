from django.shortcuts import render, redirect, get_object_or_404
#
# def list_list(request):
#     lists = List.objects.all()
#     return render(request, "lists/list_list.html", {"lists": lists})
#
# def list_create(request):
#     if request.method == "POST":
#         name = request.POST.get("name")
#         List.objects.create(name=name)
#         return redirect("list_list")
#     return render(request, "lists/list_create.html")
#
# def list_detail(request, list_id):
#     lst = get_object_or_404(List, pk=list_id)
#     return render(request, "lists/list_detail.html", {"list": lst})
#
# def list_rename(request, list_id):
#     lst = get_object_or_404(List, pk=list_id)
#     if request.method == "POST":
#         lst.name = request.POST.get("name")
#         lst.save()
#         return redirect("list_detail", list_id=list_id)
#     return render(request, "lists/list_rename.html", {"list": lst})
#
# def list_delete(request, list_id):
#     lst = get_object_or_404(List, pk=list_id)
#     if request.method == "POST":
#         lst.delete()
#         return redirect("list_list")
#     return render(request, "lists/list_delete.html", {"list": lst})
#
# def list_items_partial(request, list_id):
#     items = ListItem.objects.filter(list_id=list_id)
#     return render(request, "lists/partials/items.html", {"items": items, "list_id": list_id})
#
# def list_item_add(request, list_id):
#     if request.method == "POST":
#         movie_id = request.POST.get("movie_id")
#         ListItem.objects.create(list_id=list_id, movie_id=movie_id)
#         return list_items_partial(request, list_id)
#     return redirect("list_detail", list_id=list_id)
#
# def list_item_delete(request, list_id, item_id):
#     if request.method == "POST":
#         item = get_object_or_404(ListItem, pk=item_id, list_id=list_id)
#         item.delete()
#         return list_items_partial(request, list_id)
#     return redirect("list_detail", list_id=list_id)
