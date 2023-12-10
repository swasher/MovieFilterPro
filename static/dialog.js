;(function () {
  const modal = new bootstrap.Modal(document.getElementById("modalform"))

  htmx.on("htmx:afterSwap", (e) => {
    // Response targeting #dialog => show the modal
    console.log(1)
    if (e.detail.target.id === "dialog") {
      modal.show()
      console.log('1a')
    }
  })

  htmx.on("htmx:beforeSwap", (e) => {
    // Empty response targeting #dialog => hide the modal
    console.log(2)
    if (e.detail.target.id === "dialog" && e.detail.xhr.status === 204) {
      console.log('2a')
      modal.hide()
      e.detail.shouldSwap = false

      document.getElementById('kinorium-table').dispatchEvent(new Event('refreshEvent'));

    }
  })

  // Remove dialog content after hiding
  htmx.on("hidden.bs.modal", () => {
    console.log(3)
    document.getElementById("dialog").innerHTML = ""
  })
})()
