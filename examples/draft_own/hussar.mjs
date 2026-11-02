// A hussar jacket body drafted on bent's block (T5 proof): fronts edge to edge for a zip with the hem cut away to a
// point at centre front, back panels with a centre-back seam, a tall stand collar, bent's two-piece sleeve.
import { Design } from '@freesewing/core'
import { back as bentBack, front as bentFront, topsleeve, undersleeve } from '@freesewing/bent'

const HEM = 30 // side hem: this far below the waist (mm)
const POINT = 95 // the cutaway's point at centre front: this far below the waist
const COLLAR_H = 48, COLLAR_IN = 10 // the stand: height, and how far its top edge comes in at each end
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
    points.hem2 = new Point(points.hem.x, points.cfWaist.y + HEM)
    points.cfPoint = new Point(0, points.cfWaist.y + POINT)
    points.cutCp = new Point(points.hem2.x * 0.45, points.cfPoint.y)
    store.set('frontNeck', paths.frontCollar.length())
    paths.seam = new Path().move(points.cfNeck).line(points.cfPoint)._curve(points.cutCp, points.hem2)
      .line(points.armhole).curve(points.armholeCp2, points.armholeHollowCp1, points.armholeHollow)
      .curve(points.armholeHollowCp2, points.armholePitchCp1, points.armholePitch).join(paths.frontArmhole)
      .line(points.s3CollarSplit).join(paths.frontCollar).close()
    return part
  },
}

const collar = {
  name: 'hussar.collar', after: [back, front],
  draft: ({ points, Point, paths, Path, store, snippets, Snippet, part }) => {
    const L = 2 * (store.get('frontNeck') + store.get('backNeck'))
    points.bl = new Point(0, COLLAR_H); points.bm = new Point(L / 2, COLLAR_H); points.br = new Point(L, COLLAR_H)
    points.tr = new Point(L - COLLAR_IN, 0); points.tl = new Point(COLLAR_IN, 0)
    snippets.hook = new Snippet('button', new Point(6, COLLAR_H / 2))
    snippets.eye = new Snippet('buttonhole', new Point(L - 6, COLLAR_H / 2))
    paths.seam = new Path().move(points.bl).line(points.bm).line(points.br).line(points.tr).line(points.tl).close()
    return part
  },
}

const top = { name: 'hussar.topsleeve', from: topsleeve, after: [back, front], hide: HIDE,
  draft: ({ part }) => part }
const under = { name: 'hussar.undersleeve', from: undersleeve, after: [back, front], hide: HIDE,
  draft: ({ part }) => part }

export default new Design({ parts: [back, front, collar, top, under] })
