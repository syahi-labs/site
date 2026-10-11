/* Click to play: nothing from YouTube loads until a visitor presses a play button. */
document.querySelectorAll(".pm-play").forEach(function (button) {
  button.hidden = false;
  button.addEventListener("click", function () {
    var card = button.closest(".pm-card");
    var frame = document.createElement("iframe");
    frame.src = "https://www.youtube-nocookie.com/embed/videoseries?list=" + encodeURIComponent(card.dataset.list) + "&autoplay=1";
    frame.title = card.dataset.title;
    frame.allow = "autoplay; encrypted-media; picture-in-picture";
    frame.allowFullscreen = true;
    card.querySelector(".pm-media").replaceChildren(frame);
    frame.focus();
  });
});
