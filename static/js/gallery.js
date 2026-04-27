"use strict";

// ---------------------------------------------------------------------------
// View switching + breadcrumb
// ---------------------------------------------------------------------------

function showView(name) {
  $("view-gallery").classList.toggle("active", name === "gallery");
  $("view-detail").classList.toggle("active", name === "detail");
  updateBreadcrumb(name);

  if (
    name === "gallery" &&
    state.activeCategory &&
    $("gallery-grid").children.length === 0 &&
    $("gallery-empty").classList.contains("hidden")
  ) {
    loadGalleryPage();
  }
}

function updateBreadcrumb(view) {
  const cat = state.activeCategory ?? "";
  const title = state.currentProduct?.title ?? "";

  $("header-category-badge").textContent = cat;
  $("header-category-badge").classList.toggle("hidden", !cat);

  if (view === "gallery") {
    $("bc-gallery").classList.add("hidden");
    $("bc-sep1").classList.add("hidden");
    $("bc-product").classList.add("hidden");
    $("bc-sep2").classList.add("hidden");
    $("bc-compare").classList.add("hidden");
  } else {
    $("bc-gallery").classList.remove("hidden");
    $("bc-sep1").classList.remove("hidden");
    $("bc-product").textContent =
      title.length > 40 ? title.slice(0, 40) + "…" : title;
    $("bc-product").classList.remove("hidden");
    // bc-sep2 and bc-compare are revealed by compare.js when results arrive
  }
}

// ---------------------------------------------------------------------------
// Categories
// ---------------------------------------------------------------------------

function updateUrl(replace = false) {
  const url = new URL(window.location.href);
  if (state.activeCategory)
    url.searchParams.set("category", state.activeCategory);
  if (state.galleryPage > 1) url.searchParams.set("page", state.galleryPage);
  else url.searchParams.delete("page");
  if (state.searchQuery) url.searchParams.set("search", state.searchQuery);
  else url.searchParams.delete("search");

  if (replace) {
    window.history.replaceState({}, "", url.toString());
  } else {
    window.history.pushState({}, "", url.toString());
  }
}

async function loadCategories() {
  try {
    const cats = await fetchJSON(`${BASE_URL}/categories`);
    // Prepend synthetic 'all' so users can search/browse across every category
    state.categories = ["all", ...cats];
    renderCategoryPills(state.categories);

    const params = new URLSearchParams(window.location.search);
    const urlCat = params.get("category");
    const urlPage = parseInt(params.get("page"), 10);
    const urlSearch = params.get("search") || "";

    if (urlSearch) {
      state.searchQuery = urlSearch;
      if ($("search-input")) $("search-input").value = urlSearch;
    }
    if (urlPage && !isNaN(urlPage) && urlPage > 0) {
      state.galleryPage = urlPage;
    }

    const urlProduct = params.get("product");
    if (urlProduct) {
      state.currentProduct = { id: urlProduct };
    }

    const catToSelect =
      urlCat && state.categories.includes(urlCat)
        ? urlCat
        : cats.length > 0
          ? cats[0]
          : null;
    if (catToSelect) {
      await selectCategory(catToSelect, false, true, !!urlProduct);
    }

    if (urlProduct) {
      openProduct(urlProduct, true);
    }
  } catch (err) {
    showToast("Failed to load categories: " + err.message, "error");
  }
}

function renderCategoryPills(cats) {
  const container = $("category-pills");
  container.innerHTML = cats
    .map(
      (c) =>
        `<button class="pill ${c === state.activeCategory ? "pill--active" : "pill--inactive"}"
                 data-cat="${esc(c)}">${c === "all" ? "All" : esc(c)}</button>`,
    )
    .join("");

  container
    .querySelectorAll(".pill")
    .forEach((btn) =>
      btn.addEventListener("click", () => selectCategory(btn.dataset.cat)),
    );
}

async function selectCategory(
  cat,
  reset = true,
  replaceUrl = false,
  skipLoad = false,
) {
  state.activeCategory = cat;
  if (reset) {
    state.galleryPage = 1;
    state.galleryTotal = 0;
    state.searchQuery = "";
    if ($("search-input")) $("search-input").value = "";
  }

  // Update pill highlight without re-rendering the full list
  $("category-pills")
    .querySelectorAll(".pill")
    .forEach((btn) => {
      const active = btn.dataset.cat === cat;
      btn.classList.toggle("pill--active", active);
      btn.classList.toggle("pill--inactive", !active);
    });

  $("header-category-badge").textContent = cat;
  $("header-category-badge").classList.remove("hidden");

  updateUrl(replaceUrl);
  if (!skipLoad) {
    await loadGalleryPage();
  }
}

// ---------------------------------------------------------------------------
// Product grid
// ---------------------------------------------------------------------------

async function loadGalleryPage() {
  renderGallerySkeleton();

  try {
    let url = `${BASE_URL}/products?category=${encodeURIComponent(state.activeCategory)}&limit=${PAGE_SIZE}&page=${state.galleryPage}`;
    if (state.searchQuery) {
      url += `&search=${encodeURIComponent(state.searchQuery)}`;
    }

    const data = await fetchJSON(url);
    const count = data.total ?? data.count;

    // Auto-fallback: if searching within a specific category gives 0 results,
    // widen to all categories transparently and notify the user.
    if (count === 0 && state.searchQuery && state.activeCategory !== "all") {
      const allUrl = `${BASE_URL}/products?category=all&limit=${PAGE_SIZE}&page=${state.galleryPage}&search=${encodeURIComponent(state.searchQuery)}`;
      const allData = await fetchJSON(allUrl);
      const allCount = allData.total ?? allData.count;
      if (allCount > 0) {
        state.galleryTotal = allCount;
        renderGallery(allData.products);
        renderPagination();
        showToast(`No results in "${state.activeCategory}" — showing ${allCount} from all categories`, "info");
        return;
      }
    }

    state.galleryTotal = count;
    renderGallery(data.products);
    renderPagination();
  } catch (err) {
    $("gallery-grid").innerHTML = "";
    showToast("Failed to load products: " + err.message, "error");
  }
}


function renderGallerySkeleton() {
  $("gallery-empty").classList.add("hidden");
  $("gallery-pagination").classList.add("hidden");

  $("gallery-grid").innerHTML = Array.from({ length: 12 })
    .map(
      () => `
        <div class="bg-surface rounded-card border border-surface-border shadow-card overflow-hidden">
          <div class="skeleton-rect h-44 w-full"></div>
          <div class="p-3 space-y-2">
            <div class="skeleton h-3 w-3/4"></div>
            <div class="skeleton h-3 w-1/2"></div>
          </div>
        </div>`,
    )
    .join("");
}

function renderGallery(products) {
  const grid = $("gallery-grid");
  grid.innerHTML = "";

  if (!products || products.length === 0) {
    $("gallery-empty").classList.remove("hidden");
    $("gallery-pagination").classList.add("hidden");
    return;
  }

  $("gallery-empty").classList.add("hidden");

  products.forEach((p) => {
    const card = document.createElement("button");
    card.className = "product-card w-full";

    // Image wrapper — uses CSS class from global.css for height + centering
    const imgWrap = document.createElement("div");
    imgWrap.className = "product-card__image";

    // Set data-src instead of src so the IntersectionObserver drives loading
    const img = document.createElement("img");
    img.dataset.src = imageUrl(p.image_path);
    img.alt = p.title ?? "";
    img.decoding = "async";
    imgWrap.appendChild(img);

    const info = document.createElement("div");
    info.className = "p-3";
    info.innerHTML = `
      <p class="text-xs font-medium text-content line-clamp-2 leading-snug">${esc(p.title)}</p>
      ${p.price ? `<p class="mt-1 text-sm font-bold text-primary-600">$${esc(p.price)}</p>` : ""}`;

    card.appendChild(imgWrap);
    card.appendChild(info);
    card.addEventListener("click", () => openProduct(p.id));

    grid.appendChild(card);

    // Register with observer AFTER the element is in the DOM
    observeLazy(img);
  });
}

// ---------------------------------------------------------------------------
// Pagination
// ---------------------------------------------------------------------------

/**
 * Render Prev / Next controls using state.galleryTotal (the real row count
 * returned by the API) so buttons are always accurately enabled/disabled.
 *
 *   totalPages = ceil(total / PAGE_SIZE)
 *   Prev   — disabled on page 1
 *   Next   — disabled on the last page
 *   Hidden — when there is only a single page
 */
function renderPagination() {
  const totalPages = Math.max(1, Math.ceil(state.galleryTotal / PAGE_SIZE));

  if (totalPages <= 1) {
    $("gallery-pagination").classList.add("hidden");
    return;
  }

  $("gallery-pagination").classList.remove("hidden");
  $("pagination-label").textContent =
    `Page ${state.galleryPage} of ${totalPages}`;
  $("btn-prev").disabled = state.galleryPage <= 1;
  $("btn-next").disabled = state.galleryPage >= totalPages;
}

$("btn-prev").addEventListener("click", async () => {
  if (state.galleryPage <= 1) return;
  state.galleryPage--;
  updateUrl();
  await loadGalleryPage();
  window.scrollTo({ top: 0, behavior: "smooth" });
});

$("btn-next").addEventListener("click", async () => {
  const totalPages = Math.ceil(state.galleryTotal / PAGE_SIZE);
  if (state.galleryPage >= totalPages) return;
  state.galleryPage++;
  updateUrl();
  await loadGalleryPage();
  window.scrollTo({ top: 0, behavior: "smooth" });
});

// ---------------------------------------------------------------------------
// Navigation listeners
// ---------------------------------------------------------------------------

if ($("search-input")) {
  $("search-input").addEventListener("input", (e) => {
    state.searchQuery = e.target.value;
  });

  $("search-input").addEventListener("keydown", async (e) => {
    if (e.key === "Enter") {
      state.galleryPage = 1;
      updateUrl();
      await loadGalleryPage();
    }
  });
}

if ($("btn-search")) {
  $("btn-search").addEventListener("click", async () => {
    state.galleryPage = 1;
    updateUrl();
    await loadGalleryPage();
  });
}

$("btn-home").addEventListener("click", () => {
  const url = new URL(window.location.href);
  url.searchParams.delete("product");
  window.history.pushState({}, "", url.toString());

  state.currentProduct = null;
  showView("gallery");
  window.scrollTo({ top: 0, behavior: "smooth" });
});

$("bc-gallery").addEventListener("click", () => {
  const url = new URL(window.location.href);
  url.searchParams.delete("product");
  window.history.pushState({}, "", url.toString());

  state.currentProduct = null;
  showView("gallery");
});

window.addEventListener("popstate", async () => {
  const params = new URLSearchParams(window.location.search);
  const urlCat = params.get("category");
  const urlPage = parseInt(params.get("page"), 10);
  const urlSearch = params.get("search") || "";
  const urlProduct = params.get("product");

  if (urlProduct) {
    state.currentProduct = { id: urlProduct };
  } else {
    state.currentProduct = null;
  }

  state.searchQuery = urlSearch;
  if ($("search-input")) $("search-input").value = urlSearch;
  state.galleryPage = urlPage && !isNaN(urlPage) && urlPage > 0 ? urlPage : 1;

  if (
    urlCat &&
    state.categories.includes(urlCat) &&
    state.activeCategory !== urlCat
  ) {
    await selectCategory(urlCat, false, false, !!urlProduct);
  } else if (!urlProduct) {
    await loadGalleryPage();
  }
});
