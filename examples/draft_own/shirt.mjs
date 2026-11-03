// A dress shirt drafted fresh on brian's block (T5 proof): back, yoke, fronts with a cut-on button extension, a one-
// piece sleeve shortened for the cuff, a barrel cuff, simon's curved collar stand (the band) and simon's collar (the fall).
import { Design } from '@freesewing/core'
import { back as brianBack, front as brianFront } from '@freesewing/brian'
import { sleeve as baseSleeve } from '@freesewing/library'
import { collarStand as simonStand, collar as simonCollar } from '@freesewing/simon'

const LEN = 1.2 // hem: the hips depth x 1.2 (an untucked shirt's length, below the seat)
const EXT = 16 // button extension past centre front (mm)
const YOKE = 0.45 // yoke seam: this far from the back neck to the back armhole pitch
const CUFF_H = 62, CUFF_EASE = 80, PLEAT = 16, BAND_H = 32, FALL = 44, TIP = 28
const HIDE = { from: true, inherited: true }
const hideAll = (paths) => { for (const k of Object.keys(paths)) paths[k].hide() }
const armholeOf = (points, Path) => new Path().move(points.armhole)
  .curve(points.armholeCp2, points.armholeHollowCp1, points.armholeHollow)
  .curve(points.armholeHollowCp2, points.armholePitchCp1, points.armholePitch)
  .curve(points.armholePitchCp2, points.shoulderCp1, points.shoulder)
const yokeSplit = (points, Point, Path) => {
  const arm = armholeOf(points, Path)
  const y = points.cbNeck.y + (points.armholePitch.y - points.cbNeck.y) * YOKE
  points.yokeArm = arm.intersectsY(y)[0]
  points.cbYoke = new Point(0, y)
  return arm.split(points.yokeArm)
}

const back = {
  name: 'shirt.back', from: brianBack, hide: HIDE,
  draft: ({ points, Point, paths, Path, part }) => {
    hideAll(paths)
    const [low] = yokeSplit(points, Point, Path)
    points.cbHem2 = new Point(0, points.cbHips.y * LEN)
    points.hem2 = new Point(points.hem.x, points.cbHem2.y)
    paths.seam = new Path().move(points.cbYoke).line(points.cbHem2).line(points.hem2).line(points.armhole)
      .join(low).line(points.cbYoke).close()
    return part
  },
}

const yoke = {
  name: 'shirt.yoke', from: brianBack, hide: HIDE,
  draft: ({ points, Point, paths, Path, store, part }) => {
    hideAll(paths)
    const [, up] = yokeSplit(points, Point, Path)
    const neck = new Path().move(points.hps).curve_(points.neckCp2, points.cbNeck)
    store.set('backNeck', neck.length())
    paths.seam = new Path().move(points.cbYoke).line(points.yokeArm).join(up).line(points.hps).join(neck)
      .line(points.cbYoke).close()
    return part
  },
}

const front = {
  name: 'shirt.front', from: brianFront, hide: HIDE,
  draft: ({ points, Point, paths, Path, store, snippets, Snippet, part }) => {
    hideAll(paths)
    points.cfHem2 = new Point(0, points.cfHips.y * LEN)
    points.hem2 = new Point(points.hem.x, points.cfHem2.y)
    points.cfHemExt = new Point(-EXT, points.cfHem2.y)
    points.cfNeckExt = new Point(-EXT, points.cfNeck.y)
    store.set('frontNeck', paths.frontCollar.length() + EXT)
    const first = points.cfNeck.y + 75, pitch = (points.cfHem2.y - 170 - first) / 6
    for (let i = 1; i <= 7; i++) {
      points[`btn${i}`] = new Point(0, first + (i - 1) * pitch)
      snippets[`btn${i}`] = new Snippet('button', points[`btn${i}`])
    }
    paths.seam = new Path().move(points.cfNeckExt).line(points.cfHemExt).line(points.cfHem2).line(points.hem2)
      .line(points.armhole).curve(points.armholeCp2, points.armholeHollowCp1, points.armholeHollow)
      .curve(points.armholeHollowCp2, points.armholePitchCp1, points.armholePitch).join(paths.frontArmhole)
      .line(points.s3CollarSplit).join(paths.frontCollar).line(points.cfNeckExt).close()
    return part
  },
}

const sleeve = {
  name: 'shirt.sleeve', from: baseSleeve, after: [back, front], hide: HIDE,
  draft: ({ points, Point, paths, Path, measurements, store, part }) => {
    hideAll(paths)
    const cuff = measurements.wrist + CUFF_EASE // closed: wrist + CUFF_EASE - 24 mm of lap, clear of the forearm
    store.set('cuffLength', cuff)
    const y = points.centerWrist.y - CUFF_H
    points.wL = new Point(-(cuff / 2 + PLEAT), y)
    points.wR = new Point(cuff / 2 + PLEAT, y)
    paths.seam = new Path().move(points.wL).line(points.wR).line(points.bicepsRight).join(paths.sleevecap)
      .line(points.wL).close()
    return part
  },
}

const cuff = {
  name: 'shirt.cuff', after: sleeve,
  draft: ({ points, Point, paths, Path, store, snippets, Snippet, part }) => {
    const L = store.get('cuffLength')
    snippets.hole = new Snippet('buttonhole', new Point(12, CUFF_H / 2))
    snippets.btn = new Snippet('button', new Point(L - 12, CUFF_H / 2))
    points.tl = new Point(0, 0); points.tr = new Point(L, 0)
    points.br = new Point(L, CUFF_H); points.bl = new Point(0, CUFF_H); points.bm = new Point(L / 2, CUFF_H)
    paths.seam = new Path().move(points.tl).line(points.bl).line(points.bm).line(points.br).line(points.tr).close()
    return part
  },
}

// The band is simon's collarStand and the fall simon's collar: a patternmaker's curves (the band's neck edge bends and
// its front ends rise: collarStandBend 0, collarStandCurve 5, simon's own rising end of its range; the fall's outer edge
// longer than its stand seam so it turns down over the band). Its button extensions = this front's EXT (the placket
// widths in options.json: 2 x EXT / neck); one collarEase (brian's default, 5 %) sizes the neckline and the band alike.
const band = {
  name: 'shirt.band', from: simonStand, after: [front, yoke],
  draft: ({ points, snippets, Snippet, part }) => {
    snippets.hole = new Snippet('buttonhole', points.leftCf)
    snippets.btn = new Snippet('button', points.rightCf)
    return part
  },
}

const collar = { name: 'shirt.collar', from: simonCollar, after: band, draft: ({ part }) => part }

export default new Design({ parts: [back, yoke, front, sleeve, cuff, band, collar] })
