# Likeness: a profile from a turned view (contours)

Read guide(topic="likeness") first.


A three-quarter picture holds a profile at a known angle: the FAR side of the face against the background (forehead,
brow ridge, the far orbit and cheek, the mouth's line, the chin's corner, the under-jaw) and the nose's own edge
against the far cheek (bridge, tip, columella). Artists trace exactly these two lines. So when there is no true
profile, trace them:

    likeness_points(name, image, lines={"profile": [[u, v], ...], "nose": [[u, v], ...]})

"profile" runs from the forehead down round the chin (a dozen points by eye are enough: it is snapped to the
picture's edge against the background when read); "nose" from between the brows down the bridge, round the tip, back
to the columella's base (by hand: +-1 px). The model's own contours are found through the same camera (its render's
silhouette; the extreme of its nose's vertices), both are read in one frame (inner eye corners -> the mouth's
corners), and the contour items compare them: forehead slope, brow ridge over the orbit, the cheek's line at the
mouth's height, chin projection (the contour's chin corner against the brow's peak), chin depth below the mouth,
mentolabial fold, upper / lower lip out of the mouth's notch, nose tip projection, the tip's gap to the far cheek's
line, nose length, the bridge's bow. They replace the "inferred ~" detector readings of the same things on that
picture. Units are mm IN THE PICTURE (a turned view foreshortens depth), read alike on both sides.

What to know before believing them:
- 1 degree of camera yaw moves the nose's gap to the cheek line by ~1 mm. A generated painting need not be one
  projection: a painting can read 31 degrees by the detector's head pose, 45 by the fitted camera, and draw its nose
  as if turned further still. The far eye corner's gap to the contour is the cross-check (it agreed
  with the fitted camera there).
- The lips are named only where a notch between them breaks the contour; at 45 degrees the far cheek usually hides
  them ("the lips don't break this contour"), and the mouth's line is then the cheek's.
- The chin "corner" is the point standing furthest out of the chord from the mouth's height to the under-jaw: it
  exists on any chin, but on a round one it slides.

The fit (`fit_likeness(name, "profile")`, also run inside the nose and chin_jaw stages when the lines exist): the
contour's miss at the model vertices that make its contour becomes targets for `humanfit.fit_region` (GNM identity
components inside the nose region / the chin + lower lip region, every other landmark held, integrity-guarded), with
the part's landmarks held where the FRONT picture has them (a turned view says how far forward things stand; heights
and widths are the front view's), one camera through all rounds, up to five rounds judged on the contour's own rms.
