// A hussar jacket body drafted on bent's block (T5 proof): fronts edge to edge for a zip with the hem cut away to a
// point at centre front, back panels with a centre-back seam, a tall stand collar, bent's two-piece sleeve.
import { Design } from '@freesewing/core'
import { back as bentBack, front as bentFront, topsleeve, undersleeve } from '@freesewing/bent'
import { collarStand as simonStand } from '@freesewing/simon'

const HEM = 120 // side hem: this far below the waist (mm): the reference ends at the hip
const CF_END = 40 // the zip's end at centre front, below the waist: the fronts are cut away from here
const TIP = [70, 135] // the cutaway's tip: this far out from CF and below the waist
const STEP_OUT = 60 // the cutaway's square step out from CF at the zip's end (mm)
const ROUND = 16 // the stand's front top corners: rounded over this much (mm; the reference's are round)
// The stand's heights, from the flat gate's shape_stand row on step 2's traced top line (level all round, 53 mm above the
// side neck, dropping 20 mm to its front ends) over the neckline SEEN (r-hussar: the collar_front traces' bottoms 49 mm
// below the side neck; the body's CB neck 9 mm above it): front ends h_side + D - T = 82, CB h_side + D_back (1 - f) = 48.
// (c1 took D from the flat, 75 mm: fronts 108 tall, built lying out.)
const H_SIDE = 53, H_CB = 48, H_FRONT = 82
// The reference's neckline at CF sits 49 mm below the side neck; c1's built 19 (its flat 75 mm drop tilts back over the
// chest): the front neck lowered at CF by the difference, the curve keeping its square corner at CF.
const NECK_DOWN = 30
const TOP_N = 24 // top-line points per half
const HIDE = { from: true, inherited: true }
const hideAll = (paths) => { for (const k of Object.keys(paths)) paths[k].hide() }

const back = {
  name: 'hussar.back', from: bentBack, hide: HIDE,
  draft: ({ points, Point, paths, Path, store, part }) => {
    hideAll(paths)
    points.cbHem2 = new Point(0, points.cbWaist.y + HEM)
    points.hem2 = new Point(points.hem.x, points.cbHem2.y)
    const neck = new Path().move(points.hps).curve_(points.neckCp2, points.cbNeck)
    store.set('backNeck', neck.length())
    paths.seam = new Path().move(points.cbNeck).line(points.cbHem2).line(points.hem2).line(points.armhole)
      .curve(points.armholeCp2, points.armholeHollowCp1, points.armholeHollow)
      .curve(points.armholeHollowCp2, points.armholePitchCp1, points.armholePitch)
      .curve(points.armholePitchCp2, points.shoulderCp1, points.shoulder).line(points.hps).join(neck).close()
    return part
  },
}

const front = {
  name: 'hussar.front', from: bentFront, hide: HIDE,
  draft: ({ points, Point, paths, Path, store, part }) => {
    hideAll(paths)
    points.cfNeck = new Point(points.cfNeck.x, points.cfNeck.y + NECK_DOWN)
    points.cfNeckCp1 = new Point(points.cfNeckCp1.x, points.cfNeckCp1.y + NECK_DOWN)
    paths.frontCollar = new Path().move(points.hps).curve(points.neckCp2Front, points.cfNeckCp1, points.cfNeck).hide()
    points.hem2 = new Point(points.hem.x, points.cfWaist.y + HEM)
    points.cfPoint = new Point(0, points.cfWaist.y + CF_END)
    // the reference's cutaway: the front edge comes down to the zip's end, steps OUT in a square corner, then drops to
    // a point; the hem runs from the point to the side (corners stay corners: traced, not an arc)
    points.cutStep = new Point(STEP_OUT, points.cfPoint.y)
    points.cutTip = new Point(TIP[0], points.cfWaist.y + TIP[1])
    store.set('frontNeck', paths.frontCollar.length())
    paths.seam = new Path().move(points.cfNeck).line(points.cfPoint).line(points.cutStep).line(points.cutTip).line(points.hem2)
      .line(points.armhole).curve(points.armholeCp2, points.armholeHollowCp1, points.armholeHollow)
      .curve(points.armholeHollowCp2, points.armholePitchCp1, points.armholePitch).join(paths.frontArmhole)
      .line(points.s3CollarSplit).join(paths.frontCollar).close()
    return part
  },
}

// The stand is simon's collarStand (a patternmaker's curved stand: its centre line bends, the edges follow), its neck
// edge sized by the same collarEase as the neckline. The reference's stand stands AWAY from the neck with its top line
// level all round, so its neck edge is near straight (simon's bend 1 deg the rising way: the row's f x 0.47 x D, f the
// share of the drop the top follows) and it is TALLER where the neckline drops: its top line is redrawn at the traced
// height above each place of the neck edge (the neckline's drop under it: a back neck rising to the side neck like
// 1 - cos, a front neck falling from it like sin), its front top corners rounded; no button extension (hooks).
const collar = {
  name: 'hussar.collar', from: simonStand, after: [back, front],
  draft: ({ points, Point, paths, Path, snippets, Snippet, store, part }) => {
    // the neck edge sized to the neckline it's sewn to (the lowered front neck is longer than simon's neck x collarEase,
    // and collarEase also sizes the bodice's neckline): the whole stand widened about CB until its neck edge matches
    const half = () => new Path().move(points.bottomMid)
      .curve(points.bottomMidCp2, points.rightBottomHingeCp1, points.rightBottomHinge)
      .curve(points.rightBottomHingeCp2, points.rightBottomCfCp1, points.rightBottomCf).length()
    for (let it = 0; it < 3; it++) {
      const k = (store.get('backNeck') + store.get('frontNeck')) / half()
      for (const n of Object.keys(points)) points[n] = new Point(points[n].x * k, points[n].y)
    }
    const bottom = new Path().move(points.bottomMid)
      .curve(points.bottomMidCp2, points.rightBottomHingeCp1, points.rightBottomHinge)
      .curve(points.rightBottomHingeCp2, points.rightBottomCfCp1, points.rightBottomCf)
    const L = bottom.length()
    const HPS_AT = store.get('backNeck') / (store.get('backNeck') + store.get('frontNeck'))  // the side neck along the half
    const height = (u) => u < HPS_AT ? H_SIDE + (H_CB - H_SIDE) * Math.cos((Math.PI / 2) * u / HPS_AT)
      : H_SIDE + (H_FRONT - H_SIDE) * Math.sin((Math.PI / 2) * (u - HPS_AT) / (1 - HPS_AT))
    const tops = []  // CB .. the front end, right side
    for (let i = 0; i <= TOP_N; i++) {
      const u = i / TOP_N
      const p = bottom.shiftAlong(Math.min(Math.max(u * L, 0.5), L - 0.5))
      const a = bottom.shiftAlong(Math.max(u * L - 0.5, 0)).angle(bottom.shiftAlong(Math.min(u * L + 0.5, L)))
      tops.push(p.shift(a + 90, height(u)))
    }
    const c = tops[TOP_N], b = points.rightBottomEdge
    points.rightEndUp = c.shiftTowards(b, ROUND)
    points.rightTopIn = c.shiftTowards(tops[TOP_N - 1], ROUND)
    points.rightEndUpCp = points.rightEndUp.shiftFractionTowards(c, 0.55)
    points.rightTopInCp = points.rightTopIn.shiftFractionTowards(c, 0.55)
    for (let i = 0; i < TOP_N; i++) {
      points['rTop' + i] = tops[i]
      points['lTop' + i] = tops[i].flipX()
    }
    for (const k of ['EndUp', 'TopIn', 'EndUpCp', 'TopInCp']) points['left' + k] = points['right' + k].flipX()
    points.topMid = tops[0]
    let path = new Path().move(points.bottomMid)
      .curve(points.bottomMidCp2, points.rightBottomHingeCp1, points.rightBottomHinge)
      .curve(points.rightBottomHingeCp2, points.rightBottomCfCp1, points.rightBottomCf).line(points.rightBottomEdge)
      .line(points.rightEndUp).curve(points.rightEndUpCp, points.rightTopInCp, points.rightTopIn)
    for (let i = TOP_N - 1; i >= 1; i--) path = path.line(points['rTop' + i])
    path = path.line(points.topMid)
    for (let i = 1; i < TOP_N; i++) path = path.line(points['lTop' + i])
    paths.seam = path.line(points.leftTopIn).curve(points.leftTopInCp, points.leftEndUpCp, points.leftEndUp)
      .line(points.leftBottomEdge).line(points.leftBottomCf)
      .curve(points.leftBottomCfCp2, points.leftBottomHingeCp1, points.leftBottomHinge)
      .curve(points.leftBottomHingeCp2, points.bottomMidCp1, points.bottomMid).close().attr('class', 'fabric')
    snippets.hook = new Snippet('button', points.leftCf)
    snippets.eye = new Snippet('buttonhole', points.rightCf)
    return part
  },
}

const top = { name: 'hussar.topsleeve', from: topsleeve, after: [back, front], hide: HIDE,
  draft: ({ part }) => part }
const under = { name: 'hussar.undersleeve', from: undersleeve, after: [back, front], hide: HIDE,
  draft: ({ part }) => part }

export default new Design({ parts: [back, front, collar, top, under] })
