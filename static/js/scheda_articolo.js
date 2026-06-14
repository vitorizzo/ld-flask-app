document.addEventListener("DOMContentLoaded", function () {
    var modalElement = document.getElementById("fullscreen-carousel-modal");
    var carouselElement = document.getElementById("productCarousel");
    var uploadForm = document.getElementById("productImageUploadForm");
    var contextMenu = document.getElementById("productImageContextMenu");
    var closeButton = document.getElementById("productSheetCloseBtn");
    var draggedImage = null;
    var contextImage = null;

    document.querySelectorAll('[data-bs-toggle="tooltip"]').forEach(function (element) {
        if (window.bootstrap && bootstrap.Tooltip) {
            bootstrap.Tooltip.getOrCreateInstance(element);
        }
    });

    function imagePlatform(image) {
        return image ? (image.dataset.sourcePlatform || "") : "";
    }

    function currentImageAssetId(image) {
        return image ? (image.dataset.assetId || "") : "";
    }

    function currentImageLabel(image) {
        return image ? ((image.alt || image.dataset.sourcePlatform || "immagine").trim()) : "immagine";
    }

    function hideContextMenu() {
        if (!contextMenu) {
            return;
        }
        contextMenu.classList.remove("show");
        contextMenu.setAttribute("aria-hidden", "true");
    }

    function showContextMenu(event) {
        if (!contextMenu) {
            return;
        }
        event.preventDefault();
        contextMenu.style.left = Math.min(event.clientX, window.innerWidth - 230) + "px";
        contextMenu.style.top = Math.min(event.clientY, window.innerHeight - 190) + "px";
        contextMenu.classList.add("show");
        contextMenu.setAttribute("aria-hidden", "false");
    }

    function publishImage(image, platforms) {
        if (!image) {
            alert("Seleziona un'immagine da pubblicare.");
            return;
        }

        var assetId = currentImageAssetId(image);
        if (!assetId) {
            alert("L'immagine selezionata non ha un riferimento pubblicabile.");
            return;
        }

        return fetch(window.location.pathname + "/images/publish", {
            method: "POST",
            headers: {
                "Content-Type": "application/json",
                "X-Requested-With": "XMLHttpRequest"
            },
            credentials: "same-origin",
            body: JSON.stringify({
                asset_id: assetId,
                platforms: platforms || []
            })
        }).then(function (response) {
            return response.json().then(function (data) {
                if (!response.ok || !data.ok) {
                    throw new Error(data.error || "Pubblicazione non riuscita");
                }
                return data;
            });
        });
    }

    function reportPublishResult(image, result) {
        if (!result) {
            return;
        }

        var successTargets = [];
        var errors = [];
        Object.keys(result.results || {}).forEach(function (key) {
            var entry = result.results[key];
            if (entry && entry.ok) {
                successTargets.push(key);
            } else if (entry && entry.error) {
                errors.push(key + ": " + entry.error);
            }
        });

        var parts = [];
        if (successTargets.length) {
            parts.push("Pubblicata su: " + successTargets.join(", "));
        }
        if (errors.length) {
            parts.push("Errori: " + errors.join(" | "));
        }
        alert(parts.join("\n") || ("Pubblicazione completata per " + currentImageLabel(image)));
    }

    function selectFirstImageForPlatform(platform) {
        if (!carouselElement || !platform) {
            return;
        }
        var images = Array.from(document.querySelectorAll("#productCarousel .carousel-item img"));
        var index = images.findIndex(function (image) {
            return imagePlatform(image) === platform;
        });
        if (index >= 0) {
            bootstrap.Carousel.getOrCreateInstance(carouselElement).to(index);
        }
    }

    if (uploadForm) {
        uploadForm.addEventListener("submit", async function (event) {
            event.preventDefault();
            var input = uploadForm.querySelector('input[type="file"]');
            if (!input || !input.files || !input.files.length) {
                return;
            }

            var submit = uploadForm.querySelector('button[type="submit"]');
            var originalText = submit ? submit.innerHTML : "";
            if (submit) {
                submit.disabled = true;
                submit.innerHTML = '<i class="fa-solid fa-circle-notch fa-spin"></i> Carico';
            }

            try {
                var formData = new FormData(uploadForm);
                var response = await fetch(uploadForm.action, {
                    method: "POST",
                    body: formData,
                    credentials: "same-origin"
                });
                var data = await response.json();
                if (!response.ok || !data.ok) {
                    throw new Error(data.error || "Upload non riuscito");
                }
                window.location.reload();
            } catch (error) {
                alert(error.message || "Upload non riuscito");
            } finally {
                if (submit) {
                    submit.disabled = false;
                    submit.innerHTML = originalText;
                }
            }
        });
    }

    document.querySelectorAll(".product-image-slot").forEach(function (slot) {
        slot.addEventListener("click", function () {
            if (slot.dataset.platformEnabled !== "1") {
                return;
            }
            selectFirstImageForPlatform(slot.dataset.platform);
        });

        slot.addEventListener("dragover", function (event) {
            if (slot.dataset.platformEnabled !== "1") {
                return;
            }
            event.preventDefault();
            slot.classList.add("product-image-slot--drop-ready");
        });

        slot.addEventListener("dragleave", function () {
            slot.classList.remove("product-image-slot--drop-ready");
        });

        slot.addEventListener("drop", function (event) {
            event.preventDefault();
            slot.classList.remove("product-image-slot--drop-ready");
            if (slot.dataset.platformEnabled !== "1" || !draggedImage) {
                return;
            }
            publishImage(draggedImage, [slot.dataset.platform]).then(function (data) {
                reportPublishResult(draggedImage, data);
                window.location.reload();
            }).catch(function (error) {
                alert(error.message || "Pubblicazione non riuscita");
            });
        });
    });

    document.addEventListener("click", hideContextMenu);
    document.addEventListener("keydown", function (event) {
        if (event.key === "Escape") {
            hideContextMenu();
        }
    });

    if (closeButton) {
        closeButton.addEventListener("click", function () {
            var fallbackUrl = closeButton.dataset.fallbackUrl || "/search/ricerca_x_descrizione";
            if (window.history.length > 1) {
                window.history.back();
            } else {
                window.location.href = fallbackUrl;
            }
        });
    }

    if (!modalElement) {
        return;
    }

    if (modalElement.parentElement !== document.body) {
        document.body.appendChild(modalElement);
    }

    modalElement.addEventListener("show.bs.modal", function () {
        document.body.classList.add("product-image-modal-open");
    });

    modalElement.addEventListener("hidden.bs.modal", function () {
        document.body.classList.remove("product-image-modal-open");
    });

    var fullscreenModal = bootstrap.Modal.getOrCreateInstance(modalElement);
    var fullscreenCarouselElement = document.getElementById("fullscreen-carousel");

    document.querySelectorAll(".product-img").forEach(function (image) {
        image.addEventListener("contextmenu", function (event) {
            contextImage = image;
            if (contextMenu) {
                contextMenu.dataset.assetId = currentImageAssetId(image);
            }
            showContextMenu(event);
        });
        image.addEventListener("dragstart", function () {
            draggedImage = image;
        });
        image.addEventListener("dragend", function () {
            draggedImage = null;
        });

        image.addEventListener("click", function () {
            var originalImages = Array.from(document.querySelectorAll("#productCarousel .carousel-item img"));
            var fullscreenImagesContainer = document.getElementById("fullscreen-carousel-images");
            var clickedIndex = Math.max(originalImages.indexOf(image), 0);

            if (!fullscreenImagesContainer || originalImages.length === 0) {
                return;
            }

            fullscreenImagesContainer.innerHTML = "";

            originalImages.forEach(function (sourceImage, index) {
                var carouselItem = document.createElement("div");
                carouselItem.classList.add("carousel-item");
                if (index === clickedIndex) {
                    carouselItem.classList.add("active");
                }

                var zoomedImage = document.createElement("img");
                zoomedImage.src = sourceImage.src;
                zoomedImage.alt = sourceImage.alt || "";
                zoomedImage.classList.add("d-block", "w-100");

                carouselItem.appendChild(zoomedImage);
                fullscreenImagesContainer.appendChild(carouselItem);
            });

            fullscreenModal.show();

            if (fullscreenCarouselElement) {
                bootstrap.Carousel.getOrCreateInstance(fullscreenCarouselElement).to(clickedIndex);
            }
        });
    });

    if (contextMenu) {
        contextMenu.querySelectorAll("button[data-platform]").forEach(function (button) {
            button.addEventListener("click", function (event) {
                event.stopPropagation();
                event.preventDefault();
                hideContextMenu();
                if (button.disabled || button.dataset.platformSupported !== "1") {
                    return;
                }
                var image = contextImage || draggedImage || document.querySelector("#productCarousel .carousel-item.active .product-img");
                publishImage(image, [button.dataset.platform]).then(function (data) {
                    reportPublishResult(image, data);
                    window.location.reload();
                }).catch(function (error) {
                    alert(error.message || "Pubblicazione non riuscita");
                });
            });
        });
    }
});
