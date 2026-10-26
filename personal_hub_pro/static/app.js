function openEdit(id, name, email, phone, category, city, notes) {
  const dialog = document.getElementById("edit-dialog");
  document.getElementById("edit-form").action = `/records/${id}/edit`;
  document.getElementById("e-name").value = name || "";
  document.getElementById("e-email").value = email || "";
  document.getElementById("e-phone").value = phone || "";
  document.getElementById("e-category").value = category || "Personal";
  document.getElementById("e-city").value = city || "";
  document.getElementById("e-notes").value = notes || "";
  dialog.showModal();
}
